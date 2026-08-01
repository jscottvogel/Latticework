import json
import os
import boto3
import urllib.request
import urllib.error
import time
import math
import decimal
import re
import statistics
from datetime import datetime, timezone, timedelta

# Helper encoder for DynamoDB numbers
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 == 0:
                return int(o)
            return float(o)
        return super(DecimalEncoder, self).default(o)

_ANTHROPIC_KEY = None
_ALPHA_VANTAGE_KEY = None

def get_anthropic_key():
    global _ANTHROPIC_KEY
    if _ANTHROPIC_KEY:
        return _ANTHROPIC_KEY
    client = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId='/buffett-screener/anthropic-api-key')
        secret_string = response.get('SecretString', '').strip()
        if not secret_string:
            return None
        try:
            secret_dict = json.loads(secret_string)
            if isinstance(secret_dict, dict):
                _ANTHROPIC_KEY = secret_dict.get('key') or secret_dict.get('apikey') or secret_dict.get('apiKey')
            else:
                _ANTHROPIC_KEY = str(secret_dict)
        except:
            _ANTHROPIC_KEY = secret_string.strip('\'"{} ')
        return _ANTHROPIC_KEY
    except Exception as e:
        print(f"Error fetching Anthropic secret: {e}")
        return None

def get_alpha_vantage_key():
    global _ALPHA_VANTAGE_KEY
    if _ALPHA_VANTAGE_KEY:
        return _ALPHA_VANTAGE_KEY
    client = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId='/buffett-screener/alpha-vantage-key')
        secret_string = response.get('SecretString', '').strip()
        if not secret_string:
            return None
        try:
            secret_dict = json.loads(secret_string)
            if isinstance(secret_dict, dict):
                _ALPHA_VANTAGE_KEY = secret_dict.get('key') or secret_dict.get('apikey') or secret_dict.get('apiKey')
            else:
                _ALPHA_VANTAGE_KEY = str(secret_dict)
        except:
            _ALPHA_VANTAGE_KEY = secret_string.strip('\'"{} ')
        return _ALPHA_VANTAGE_KEY
    except Exception as e:
        print(f"Error fetching Alpha Vantage secret: {e}")
        return None

def _call_claude(api_key, system_prompt, user_msg):
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2500,
        "system": system_prompt + "\n\nCRITICAL: YOU MUST RETURN ONLY VALID JSON. NO PREAMBLE. NO EXPLANATION.",
        "messages": [
            {"role": "user", "content": user_msg}
        ]
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res['content'][0]['text']
    except urllib.error.HTTPError as e:
        print(f"Anthropic API Error: {e.read().decode('utf-8')}")
        raise e

def _fetch_weekly_prices(ticker, api_key):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY_ADJUSTED&symbol={ticker}&apikey={api_key}"
    max_retries = 5
    retry_delay = 12 # safe sleep to reset rate limits
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                if "Note" in data or "Information" in data:
                    print(f"Rate limit hit on attempt {attempt+1} for {ticker}. Sleeping {retry_delay}s")
                    time.sleep(retry_delay)
                    continue
                
                # Check for error message
                if "Error Message" in data:
                    print(f"Alpha Vantage Error for {ticker}: {data['Error Message']}")
                    return {}
                
                raw_series = data.get('Weekly Adjusted Time Series', {})
                parsed_series = {}
                for d_str, v in raw_series.items():
                    price = v.get('5. adjusted close') or v.get('4. close')
                    if price:
                        parsed_series[d_str] = float(price)
                
                print(f"Successfully fetched {len(parsed_series)} weekly points for {ticker}")
                return parsed_series
        except Exception as e:
            print(f"API {ticker} failed on attempt {attempt+1}: {e}")
            time.sleep(3)
            
    return {}

def handler(event, context):
    print("advisorCompetitionWorker started")
    
    s3_bucket = os.environ.get('S3_BUCKET')
    rolling_table_name = os.environ.get('DYNAMODB_TABLE_ROLLING_SCORES')
    
    if not s3_bucket or not rolling_table_name:
        return {'status': 'FAILED', 'reason': 'MISSING_ENV_VARIABLES'}
        
    s3 = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    rolling_table = dynamodb.Table(rolling_table_name)
    
    # 1. Load rolling scores
    rolling_scores = []
    try:
        response = rolling_table.scan()
        rolling_scores = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = rolling_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            rolling_scores.extend(response.get('Items', []))
    except Exception as e:
        print(f"Error scanning rolling scores: {e}")
        return {'status': 'FAILED', 'reason': f"DYNAMODB_SCAN_ERROR: {str(e)}"}
        
    # Filter candidates with clean details and sort by composite score
    candidates = []
    for s in rolling_scores:
        avg_score = s.get('avgCompositeScore')
        if avg_score is not None:
            # We want investable or monitored prospects
            verdict = s.get('latestVerdict', '')
            if verdict in ['INVESTIGATE', 'MONITOR'] or s.get('isInvestable', False):
                candidates.append({
                    'ticker': s['ticker'],
                    'companyName': s.get('companyName', ''),
                    'sector': s.get('sector', ''),
                    'score': float(avg_score),
                    'thesis': s.get('latestThesis', '')[:200] # truncate to save LLM context
                })
                
    candidates.sort(key=lambda x: x['score'], reverse=True)
    # Take top 30 candidates to construct a prime universe
    candidates = candidates[:30]
    print(f"Universe candidate pool size: {len(candidates)}")
    
    if len(candidates) < 10:
        print("Not enough investable candidates to proceed.")
        return {'status': 'FAILED', 'reason': 'INSUFFICIENT_CANDIDATES'}
        
    # 2. Spawn Advisor selection LLM calls
    anthropic_key = get_anthropic_key()
    if not anthropic_key:
        return {'status': 'FAILED', 'reason': 'MISSING_ANTHROPIC_KEY'}
        
    advisor_personas = {
        'Graham': {
            'name': 'Benjamin Graham',
            'title': 'Deep Value & Margin of Safety Expert',
            'desc': 'Focuses on low valuation multiples, asset-heavy backing, low debt, and high downside protection.',
            'system_prompt': 'You are Benjamin Graham, the legendary father of value investing. You favor cheap assets and deep value screens.',
            'prompt': 'Select exactly 10 stocks from the provided list that best fit your deep value, margin of safety criteria. Assign a percentage weight to each (must sum to 100%, weight between 5% and 20% each). Return valid JSON only.'
        },
        'Munger': {
            'name': 'Charlie Munger',
            'title': 'High-Quality Moats & Brand compounder',
            'desc': 'Focuses on strong brand competitive advantages, high return on capital (ROIC), gross margins, and pricing power.',
            'system_prompt': 'You are Charlie Munger, the partner of Warren Buffett. You favor outstanding businesses with durable competitive moats at fair prices.',
            'prompt': 'Select exactly 10 stocks from the provided list that represent the highest quality companies with strong competitive moats. Assign a percentage weight to each (must sum to 100%, weight between 5% and 20% each). Return valid JSON only.'
        },
        'Fisher': {
            'name': 'Philip Fisher',
            'title': 'High Growth & Innovation Specialist',
            'desc': 'Focuses on organic revenue momentum, outstanding management capabilities, heavy R&D compounds, and market cap scalability.',
            'system_prompt': 'You are Philip Fisher, pioneer of growth investing. You look for businesses with massive tailwinds and scuttlebutt research scores.',
            'prompt': 'Select exactly 10 stocks from the provided list that display the strongest structural growth, R&D reinvestment, and product superiority. Assign a percentage weight to each (must sum to 100%, weight between 5% and 20% each). Return valid JSON only.'
        }
    }
    
    candidates_json = json.dumps(candidates)
    advisors_selections = {}
    
    for adv_id, info in advisor_personas.items():
        print(f"Calling LLM for advisor: {info['name']}")
        user_msg = f"Candidate stocks pool:\n{candidates_json}\n\nTask:\n{info['prompt']}\n\nFormat your output strictly as a JSON object containing two fields:\n1. 'selections': a list of objects with 'ticker' (string) and 'weight' (number, representing percentage, e.g. 15 for 15%).\n2. 'thesis': a short paragraph (max 300 characters) explaining your portfolio thesis based on your philosophy."
        
        raw_llm_out = ""
        parsed_selections = []
        parsed_thesis = ""
        
        try:
            raw_llm_out = _call_claude(anthropic_key, info['system_prompt'], user_msg)
            # Find the JSON brackets in case of formatting clutter
            match = re.search(r'\{.*\}', raw_llm_out, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                data = json.loads(raw_llm_out)
                
            raw_selections = data.get('selections', [])
            parsed_thesis = str(data.get('thesis', ''))[:300]
            
            # Validate selections schema
            total_w = 0
            for s in raw_selections:
                ticker = s.get('ticker')
                weight = s.get('weight')
                if ticker and weight:
                    # Verify ticker exists in our candidate universe
                    matched_cand = next((c for c in candidates if c['ticker'] == ticker), None)
                    if matched_cand:
                        parsed_selections.append({
                            'ticker': ticker,
                            'companyName': matched_cand['companyName'],
                            'weight': float(weight) / 100.0 # convert to decimal fraction
                        })
                        total_w += float(weight)
            
            # Normalize weights if they do not sum to 100% exactly
            if parsed_selections:
                sum_weights = sum(s['weight'] for s in parsed_selections)
                for s in parsed_selections:
                    s['weight'] = s['weight'] / sum_weights
            else:
                # Fallback to top 10 candidates equal weight
                for c in candidates[:10]:
                    parsed_selections.append({
                        'ticker': c['ticker'],
                        'companyName': c['companyName'],
                        'weight': 0.10
                    })
                parsed_thesis = "Fallback portfolio constructed based on top-rated candidates due to parsing limits."
                
        except Exception as e:
            print(f"Error parsing LLM selection for {adv_id}: {e}. Raw response: {raw_llm_out}")
            # Fallback to equal weight
            parsed_selections = []
            for c in candidates[:10]:
                parsed_selections.append({
                    'ticker': c['ticker'],
                    'companyName': c['companyName'],
                    'weight': 0.10
                })
            parsed_thesis = "Fallback portfolio of top 10 stocks assigned due to an API error."
            
        advisors_selections[adv_id] = {
            'name': info['name'],
            'title': info['title'],
            'desc': info['desc'],
            'selections': parsed_selections,
            'thesis': parsed_thesis
        }

    # 3. Fetch weekly prices for candidate pool + SPY
    av_key = get_alpha_vantage_key()
    if not av_key:
        return {'status': 'FAILED', 'reason': 'MISSING_ALPHA_VANTAGE_KEY'}
        
    unique_tickers = set(['SPY'])
    for c in candidates:
        unique_tickers.add(c['ticker'])
            
    print(f"Fetching weekly histories for candidate pool ({len(unique_tickers)} tickers)...")
    price_database = {}
    for ticker in sorted(unique_tickers):
        prices = _fetch_weekly_prices(ticker, av_key)
        if prices:
            price_database[ticker] = prices
            
    if 'SPY' not in price_database or not price_database['SPY']:
        print("Error: Could not retrieve S&P 500 benchmark prices.")
        return {'status': 'FAILED', 'reason': 'BENCHMARK_FETCH_ERROR'}
        
    # Get all sorted dates from SPY
    spy_dates = sorted(list(price_database['SPY'].keys()))
    if len(spy_dates) < 260:
        print(f"Warning: SPY dates list is short ({len(spy_dates)}). We will backtest on available length.")
        
    # 4. Construct Consistent Beater portfolio
    beater_selections = []
    beater_candidates = []
    
    spy_series = price_database['SPY']
    for c in candidates:
        ticker = c['ticker']
        t_series = price_database.get(ticker, {})
        if not t_series:
            continue
            
        outperform_years = 0
        for y in range(5):
            end_idx = len(spy_dates) - 1 - (y * 52)
            start_idx = len(spy_dates) - 1 - ((y + 1) * 52)
            if start_idx < 0:
                break
                
            start_date = spy_dates[start_idx]
            end_date = spy_dates[end_idx]
            
            spy_start = spy_series.get(start_date)
            spy_end = spy_series.get(end_date)
            t_start = t_series.get(start_date)
            t_end = t_series.get(end_date)
            
            if spy_start and spy_end and t_start and t_end:
                spy_ret = (float(spy_end) / float(spy_start)) - 1.0
                t_ret = (float(t_end) / float(t_start)) - 1.0
                if t_ret > spy_ret:
                    outperform_years += 1
                    
        c['outperform_years'] = outperform_years
        if outperform_years >= 3:
            beater_candidates.append(c)
            
    # Fallback if no candidate beat S&P 500 in 3 of 5 years
    if not beater_candidates:
        print("No candidates beat S&P 500 3/5 years. Falling back to highest outperformance count...")
        max_outperform = max([c.get('outperform_years', 0) for c in candidates]) if candidates else 0
        if max_outperform > 0:
            beater_candidates = [c for c in candidates if c.get('outperform_years', 0) == max_outperform]
        else:
            beater_candidates = candidates[:10]
            
    # Construct portfolio selections (equal weighted)
    num_beaters = len(beater_candidates)
    weight_val = 1.0 / float(num_beaters)
    for c in beater_candidates:
        beater_selections.append({
            'ticker': c['ticker'],
            'companyName': c['companyName'],
            'weight': weight_val
        })
        
    beater_thesis = f"Constructed systematically by selecting {num_beaters} candidate stocks that beat the S&P 500 in at least 3 of the last 5 years, equal-weighted."
    
    advisors_selections['Beater'] = {
        'name': 'Consistent Beater',
        'title': 'Quantitative Outperformance Rule',
        'desc': 'Systematically selects all stocks from the candidate universe that outperformed the S&P 500 index in at least 3 of the last 5 years.',
        'selections': beater_selections,
        'thesis': beater_thesis
    }
    
    # 5. Backtest horizons
    horizons = {
        '6M': {'weeks': 26, 'label': 'Last 6 Months'},
        '1Y': {'weeks': 52, 'label': 'Last 1 Year'},
        '2Y': {'weeks': 104, 'label': 'Last 2 Years'},
        '3Y': {'weeks': 156, 'label': 'Last 3 Years'},
        '5Y': {'weeks': 260, 'label': 'Last 5 Years'}
    }
    
    results = {}
    rf_annual = 0.04
    rf_weekly = rf_annual / 52.0
    
    for h_id, h_info in horizons.items():
        weeks_count = h_info['weeks']
        if len(spy_dates) < weeks_count:
            weeks_count = len(spy_dates)
            
        # Extract date range (most recent dates)
        h_dates = spy_dates[-weeks_count:]
        if not h_dates:
            continue
            
        start_date = h_dates[0]
        end_date = h_dates[-1]
        
        # Calculate initial adjusted close base prices
        base_prices = {}
        for ticker in price_database.keys():
            t_series = price_database[ticker]
            # Try to get price on start_date, or forward fill from first available
            price = t_series.get(start_date)
            if price is None:
                # pre-IPO fallback: find the earliest available price
                avail_dates = sorted(list(t_series.keys()))
                if avail_dates:
                    price = t_series[avail_dates[0]]
                else:
                    price = 1.0 # fallback
            base_prices[ticker] = price
            
        # Simulating weekly timeline
        timeline = []
        portfolio_series = {adv_id: [] for adv_id in advisors_selections.keys()}
        spy_series = []
        
        for date in h_dates:
            row = {'date': date}
            
            # SPY value
            spy_price = price_database['SPY'].get(date, base_prices['SPY'])
            spy_val = (spy_price / base_prices['SPY']) * 10000.0
            row['SPY'] = spy_val
            spy_series.append(spy_val)
            
            # Compute each advisor portfolio value
            for adv_id, adv_data in advisors_selections.items():
                p_val = 0.0
                for s in adv_data['selections']:
                    ticker = s['ticker']
                    weight = s['weight']
                    t_series = price_database.get(ticker, {})
                    ticker_price = t_series.get(date, base_prices.get(ticker, 1.0))
                    # Pre-inception fallback: holding cash
                    if date not in t_series:
                        p_val += weight * 10000.0 # cash value remains constant
                    else:
                        p_val += weight * (ticker_price / base_prices.get(ticker, 1.0)) * 10000.0
                row[adv_id] = p_val
                portfolio_series[adv_id].append(p_val)
                
            timeline.append(row)
            
        # Compute summary stats
        leaderboard = []
        
        # Benchmark weekly returns
        spy_returns = []
        for i in range(1, len(spy_series)):
            spy_returns.append((spy_series[i] / spy_series[i-1]) - 1.0)
            
        spy_total_ret = (spy_series[-1] / 10000.0) - 1.0
        spy_ann_ret = (spy_series[-1] / 10000.0) ** (52.0 / len(h_dates)) - 1.0
        spy_var = statistics.variance(spy_returns) if len(spy_returns) >= 2 else 0.0001
        
        for adv_id, adv_data in advisors_selections.items():
            p_vals = portfolio_series[adv_id]
            p_returns = []
            for i in range(1, len(p_vals)):
                p_returns.append((p_vals[i] / p_vals[i-1]) - 1.0)
                
            total_ret = (p_vals[-1] / 10000.0) - 1.0
            ann_ret = (p_vals[-1] / 10000.0) ** (52.0 / len(h_dates)) - 1.0
            
            # Annualized Sharpe
            mean_ret = statistics.mean(p_returns) if p_returns else 0.0
            stdev = statistics.stdev(p_returns) if len(p_returns) >= 2 else 0.0001
            if stdev < 0.0001:
                stdev = 0.0001
            weekly_sharpe = (mean_ret - rf_weekly) / stdev
            ann_sharpe = weekly_sharpe * math.sqrt(52.0)
            
            # Beta
            if len(p_returns) >= 2 and len(spy_returns) >= 2:
                covariance = sum((p_returns[i] - mean_ret) * (spy_returns[i] - statistics.mean(spy_returns)) for i in range(len(p_returns))) / (len(p_returns) - 1)
                beta = covariance / spy_var
            else:
                beta = 1.0
                
            # Alpha
            alpha = ann_ret - (rf_annual + beta * (spy_ann_ret - rf_annual))
            
            # Max Drawdown
            peak = -999999.0
            max_dd = 0.0
            for v in p_vals:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
                    
            leaderboard.append({
                'advisorId': adv_id,
                'name': adv_data['name'],
                'title': adv_data['title'],
                'totalReturn': total_ret,
                'annualizedReturn': ann_ret,
                'sharpe': ann_sharpe,
                'maxDrawdown': max_dd,
                'alpha': alpha,
                'beta': beta
            })
            
        # Add S&P 500 benchmark as an entity in the leaderboard
        spy_peak = -999999.0
        spy_max_dd = 0.0
        for v in spy_series:
            if v > spy_peak:
                spy_peak = v
            dd = (spy_peak - v) / spy_peak if spy_peak > 0 else 0.0
            if dd > spy_max_dd:
                spy_max_dd = dd
                
        leaderboard.append({
            'advisorId': 'SPY',
            'name': 'S&P 500 Index',
            'title': 'Market Benchmark',
            'totalReturn': spy_total_ret,
            'annualizedReturn': spy_ann_ret,
            'sharpe': (statistics.mean(spy_returns) - rf_weekly) / (statistics.stdev(spy_returns) if len(spy_returns) >= 2 else 0.0001) * math.sqrt(52.0),
            'maxDrawdown': spy_max_dd,
            'alpha': 0.0,
            'beta': 1.0
        })
        
        # Sort leaderboard by totalReturn descending
        leaderboard.sort(key=lambda x: x['totalReturn'], reverse=True)
        
        results[h_id] = {
            'label': h_info['label'],
            'startDate': start_date,
            'endDate': end_date,
            'timeline': timeline,
            'leaderboard': leaderboard
        }
        
    # 5. Build S3 payload
    export_payload = {
        'updatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'advisors': advisors_selections,
        'horizons': results
    }
    
    try:
        s3.put_object(
            Bucket=s3_bucket,
            Key='dashboard/advisor_competition.json',
            Body=json.dumps(export_payload, cls=DecimalEncoder, default=str),
            ContentType='application/json'
        )
        print("Successfully exported advisor_competition.json to S3.")
    except Exception as e:
        print(f"Error exporting advisor competition to S3: {e}")
        return {'status': 'FAILED', 'reason': f"S3_WRITE_ERROR: {str(e)}"}
        
    return {
        'status': 'SUCCESS',
        'advisors': list(advisors_selections.keys()),
        'horizons_calculated': list(results.keys())
    }
