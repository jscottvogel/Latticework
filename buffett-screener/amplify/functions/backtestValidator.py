import json
import os
import boto3
import time
import re
from datetime import datetime, timezone, timedelta
import decimal
import urllib.request
import urllib.error

# Caching for API key
_ALPHA_VANTAGE_KEY = None

def get_secret(secret_name):
    global _ALPHA_VANTAGE_KEY
    if _ALPHA_VANTAGE_KEY:
        return _ALPHA_VANTAGE_KEY
    client = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret_string = response.get('SecretString', '').strip()
        if not secret_string:
            return None
        try:
            secret_dict = json.loads(secret_string)
            if isinstance(secret_dict, dict):
                _ALPHA_VANTAGE_KEY = secret_dict.get('key') or secret_dict.get('apikey') or secret_dict.get('apiKey')
            else:
                _ALPHA_VANTAGE_KEY = str(secret_dict)
        except (json.JSONDecodeError, TypeError):
            match = re.search(r'[\'"]?(?:key|apikey|apiKey)[\'"]?\s*[:=]\s*[\'"]?([A-Za-z0-9\-]+)[\'"]?', secret_string)
            if match:
                _ALPHA_VANTAGE_KEY = match.group(1)
            else:
                _ALPHA_VANTAGE_KEY = secret_string.strip('\'"{} ')
        return _ALPHA_VANTAGE_KEY
    except Exception as e:
        print(f"Error fetching secret: {e}")
        return None

def _fetch_av_history(ticker, api_key):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={ticker}&outputsize=full&entitlement=delayed&apikey={api_key}"
    max_retries = 5
    retry_delay = 60
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            start_t = time.time()
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                ms = int((time.time() - start_t) * 1000)
                
                if "Note" in data:
                    print(f"Rate limit hit (Note) on attempt {attempt+1} for {ticker}. Sleeping {retry_delay}s")
                    time.sleep(retry_delay)
                    continue
                if "Information" in data:
                    print(f"Rate limit hit (Information) on attempt {attempt+1} for {ticker}. Sleeping {retry_delay}s")
                    time.sleep(retry_delay)
                    continue
                
                print(f"API TIME_SERIES_DAILY_ADJUSTED {ticker} - {ms}ms - 200")
                return data.get('Time Series (Daily)', {})
        except Exception as e:
            print(f"API {ticker} failed on attempt {attempt+1}: {e}")
            time.sleep(5)
            
    return {}

def get_price_on_or_after(time_series, target_date_str):
    if not time_series:
        return None, None
    try:
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except Exception as e:
        print(f"Failed to parse target date {target_date_str}: {e}")
        return None, None
    
    available_dates = []
    for d in time_series.keys():
        try:
            available_dates.append(datetime.strptime(d, "%Y-%m-%d").date())
        except ValueError:
            pass
            
    available_dates.sort()
    
    for d in available_dates:
        if d >= target_dt:
            date_str = d.strftime("%Y-%m-%d")
            day_data = time_series[date_str]
            price = day_data.get('5. adjusted close') or day_data.get('4. close')
            if price is not None:
                return float(price), date_str
    return None, None

def pearson_correlation(x_list, y_list):
    n = len(x_list)
    if n < 2:
        return 0.0
    mean_x = sum(x_list) / n
    mean_y = sum(y_list) / n
    
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_list, y_list))
    den_x = sum((x - mean_x) ** 2 for x in x_list)
    den_y = sum((y - mean_y) ** 2 for y in y_list)
    
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / ((den_x * den_y) ** 0.5)

def get_anthropic_key():
    client = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId='/buffett-screener/anthropic-api-key')
        secret_string = response.get('SecretString', '').strip()
        if not secret_string:
            return None
        try:
            secret_dict = json.loads(secret_string)
            if isinstance(secret_dict, dict):
                return secret_dict.get('key') or secret_dict.get('apikey') or secret_dict.get('apiKey')
            else:
                return str(secret_dict)
        except:
            return secret_string.strip('\'"{} ')
    except Exception as e:
        print(f"Error fetching Anthropic API key in validator: {e}")
        return None

def _call_anthropic_api(api_key, sys_prompt, user_msg):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 4000,
        "system": sys_prompt,
        "messages": [
            {"role": "user", "content": user_msg}
        ]
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data['content'][0]['text']
    except Exception as e:
        print(f"Error calling Anthropic API in tuner: {e}")
        return None

def run_prompt_auto_tuning(matched_pairs, composite_correlation, s3_bucket):
    if not s3_bucket:
        return
        
    print(f"Evaluating prompt self-tuning. Current composite correlation: {composite_correlation:.4f}")
    
    # Check if correlation is poor (< 0.15) and we have enough data (>= 5 outcomes)
    if composite_correlation >= 0.15:
        print("Correlation is healthy. Skipping auto-tuning.")
        return
        
    if len(matched_pairs) < 5:
        print(f"Not enough matured outcomes for auto-tuning ({len(matched_pairs)}/5). Skipping.")
        return
        
    api_key = get_anthropic_key()
    if not api_key:
        print("Anthropic API key not found. Skipping auto-tuning.")
        return
        
    # Get current prompt from S3 or fallback
    s3_client = boto3.client('s3')
    current_prompt = None
    try:
        obj = s3_client.get_object(Bucket=s3_bucket, Key='prompts/active_system_prompt.txt')
        current_prompt = obj['Body'].read().decode('utf-8')
    except:
        pass
        
    if not current_prompt:
        try:
            from aiScorer import BUFFETT_SYSTEM_PROMPT
            current_prompt = BUFFETT_SYSTEM_PROMPT
        except:
            current_prompt = "Buffett-style investing analyst prompt."

    # Identify mismatches
    false_positives = []
    false_negatives = []
    good_predictions = []
    
    for pair in matched_pairs:
        ticker = pair['score'].get('ticker')
        comp_score = float(pair['score'].get('compositeScore', 0.0))
        ret = float(pair['outcome'].get('excessReturnPct', 0.0))
        thesis = pair['score'].get('oneLineThesis', 'N/A')
        red_flags = pair['score'].get('redFlags', [])
        
        info = {
            'ticker': ticker,
            'score': comp_score,
            'excessReturn': f"{ret:.1%}",
            'thesis': thesis,
            'redFlags': red_flags
        }
        
        if comp_score >= 7.5 and ret <= -0.02:
            false_positives.append(info)
        elif comp_score < 5.5 and ret >= 0.02:
            false_negatives.append(info)
        elif comp_score >= 7.0 and ret >= 0.02:
            good_predictions.append(info)
            
    if not false_positives and not false_negatives:
        print("No outlier mismatches detected to learn from. Skipping auto-tuning.")
        return
        
    print(f"Running prompt auto-tuning. False Positives: {len(false_positives)}, False Negatives: {len(false_negatives)}")
    
    mismatches_summary = json.dumps({
        'false_positives': false_positives[:5],
        'false_negatives': false_negatives[:5],
        'good_predictions': good_predictions[:5]
    }, indent=2)
    
    meta_prompt = """You are a Meta-Prompt Optimizer for a Warren Buffett value-investing stock screener.
The screener uses a system prompt to evaluate stocks. However, backtesting shows the predictive accuracy is low.
The realized correlation between the AI composite scores and realized excess returns is low/negative.

Here is the CURRENT system prompt:
==================================================
{current_prompt}
==================================================

Here is a summary of matured stock recommendations from our backtest:
==================================================
{mismatches_summary}
==================================================

Your Goal:
Analyze the mismatches (False Positives and False Negatives) and the successful cases (Good Predictions).
Identify specific loopholes or criteria in the rubric that caused the model to over-rate bad candidates or under-rate good candidates.
Then, output an OPTIMIZED system prompt that refines the guidelines, scoring rubric, or red flags logic to minimize these errors in the future while retaining the core value-investing philosophy.

CRITICAL RULES:
1. Retain the exact JSON output structure (ticker, company_name, scores, composite_score, one_line_thesis, key_risks, red_flags, verdict, confidence, revenue_exposure).
2. Do not change the composite score formula.
3. Return ONLY the new system prompt inside a code block starting with ```text. Do not include any other explanations, preamble, or markdown formatting outside the code block."""

    user_msg = meta_prompt.format(
        current_prompt=current_prompt,
        mismatches_summary=mismatches_summary
    )
    
    meta_sys_prompt = "You are a prompt engineering expert specialized in financial valuation prompts."
    new_prompt_raw = _call_anthropic_api(api_key, meta_sys_prompt, user_msg)
    
    if not new_prompt_raw:
        print("Prompt optimizer call failed.")
        return
        
    match = re.search(r'```text\s*(.*?)\s*```', new_prompt_raw, re.DOTALL)
    if not match:
        match = re.search(r'```json\s*(.*?)\s*```', new_prompt_raw, re.DOTALL)
    if not match:
        match = re.search(r'```\s*(.*?)\s*```', new_prompt_raw, re.DOTALL)
        
    optimized_prompt = match.group(1).strip() if match else new_prompt_raw.strip()
    
    if len(optimized_prompt) > 500 and "composite_score" in optimized_prompt:
        try:
            s3_client.put_object(
                Bucket=s3_bucket,
                Key='prompts/active_system_prompt.txt',
                Body=optimized_prompt,
                ContentType='text/plain'
            )
            print("Successfully updated active system prompt in S3!")
        except Exception as e:
            print(f"Failed to write optimized prompt to S3: {e}")
    else:
        print("Optimized prompt failed sanity check. Not saving.")

def export_validation_summary(s3_client, s3_bucket, outcomes, stock_scores_map):
    horizons = [30, 90, 365]
    summary_data = {
        "updatedAt": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "horizons": {}
    }
    
    correlations_30 = None
    matched_pairs_30 = []
    
    for horizon in horizons:
        horizon_outcomes = [o for o in outcomes if int(o['horizonDays']) == horizon]
        
        # Match scores
        matched_pairs = []
        investigate_high_count = 0
        investigate_high_beat_count = 0
        
        for o in horizon_outcomes:
            run_id = o['runId']
            ticker = o['ticker']
            score_item = stock_scores_map.get((run_id, ticker))
            
            if score_item:
                matched_pairs.append({
                    'outcome': o,
                    'score': score_item
                })
                
                # Check verdict calibration
                verdict = score_item.get('verdict', '').upper()
                confidence = score_item.get('confidence', '').upper()
                
                if verdict == 'INVESTIGATE' and confidence == 'HIGH':
                    investigate_high_count += 1
                    if float(o.get('excessReturnPct', 0.0)) > 0:
                        investigate_high_beat_count += 1
                        
        # Compute correlations
        correlations = {}
        if len(matched_pairs) >= 2:
            excess_returns = [float(p['outcome']['excessReturnPct']) for p in matched_pairs]
            
            def get_val(s, key):
                val = s.get(key)
                if val is None:
                    return 0.0
                return float(val)
                
            correlations['moat'] = pearson_correlation([get_val(p['score'], 'scoreMoat') for p in matched_pairs], excess_returns)
            correlations['financialHealth'] = pearson_correlation([get_val(p['score'], 'scoreFinancialHealth') for p in matched_pairs], excess_returns)
            correlations['management'] = pearson_correlation([get_val(p['score'], 'scoreManagement') for p in matched_pairs], excess_returns)
            correlations['simplicity'] = pearson_correlation([get_val(p['score'], 'scoreSimplicity') for p in matched_pairs], excess_returns)
            correlations['marginOfSafety'] = pearson_correlation([get_val(p['score'], 'scoreMarginOfSafety') for p in matched_pairs], excess_returns)
            correlations['composite'] = pearson_correlation([get_val(p['score'], 'compositeScore') for p in matched_pairs], excess_returns)
        else:
            correlations = {
                'moat': 0.0,
                'financialHealth': 0.0,
                'management': 0.0,
                'simplicity': 0.0,
                'marginOfSafety': 0.0,
                'composite': 0.0
            }
            
        beat_rate = investigate_high_beat_count / investigate_high_count if investigate_high_count > 0 else 0.0
        
        # Tier-based beat rates
        tiers = {
            "tier1": {"name": ">= 8.0 (Excellent)", "count": 0, "beat": 0},
            "tier2": {"name": "7.0 to 8.0 (Good)", "count": 0, "beat": 0},
            "tier3": {"name": "5.0 to 7.0 (Neutral)", "count": 0, "beat": 0},
            "tier4": {"name": "< 5.0 (Avoid)", "count": 0, "beat": 0}
        }
        
        for pair in matched_pairs:
            comp_score = float(pair['score'].get('compositeScore', 0.0))
            is_beat = float(pair['outcome'].get('excessReturnPct', 0.0)) > 0
            
            if comp_score >= 8.0:
                key = "tier1"
            elif comp_score >= 7.0:
                key = "tier2"
            elif comp_score >= 5.0:
                key = "tier3"
            else:
                key = "tier4"
                
            tiers[key]["count"] += 1
            if is_beat:
                tiers[key]["beat"] += 1
                
        tier_data = []
        for tk, tv in tiers.items():
            rate = tv["beat"] / tv["count"] if tv["count"] > 0 else 0.0
            tier_data.append({
                "tier": tk,
                "name": tv["name"],
                "count": tv["count"],
                "beatCount": tv["beat"],
                "beatRate": round(rate, 4)
            })
            
        raw_pairs_data = []
        for p in matched_pairs:
            raw_pairs_data.append({
                'runId': p['outcome']['runId'],
                'ticker': p['outcome']['ticker'],
                'score': float(p['score'].get('compositeScore', 0.0)),
                'verdict': p['score'].get('verdict', 'N/A'),
                'stockReturn': float(p['outcome'].get('stockReturnPct', 0.0)),
                'spReturn': float(p['outcome'].get('spReturnPct', 0.0)),
                'date': p['outcome'].get('scoreSnapshotDate', '')
            })

        summary_data["horizons"][str(horizon)] = {
            "count": len(horizon_outcomes),
            "correlations": correlations,
            "calibration": {
                "investigateHighCount": investigate_high_count,
                "investigateHighBeatCount": investigate_high_beat_count,
                "investigateHighBeatRate": beat_rate
            },
            "tiers": tier_data,
            "rawPairs": raw_pairs_data
        }
        
        if horizon == 30:
            correlations_30 = correlations.get('composite', 0.0)
            matched_pairs_30 = matched_pairs
        
    if s3_bucket:
        try:
            s3_client.put_object(
                Bucket=s3_bucket,
                Key='dashboard/validation_summary.json',
                Body=json.dumps(summary_data, default=str),
                ContentType='application/json'
            )
            print("Successfully exported validation summary to S3.")
        except Exception as e:
            print(f"Error exporting validation summary to S3: {e}")
            
    if correlations_30 is not None and s3_bucket:
        try:
            run_prompt_auto_tuning(matched_pairs_30, correlations_30, s3_bucket)
        except Exception as tune_err:
            print(f"Error running auto-tuning: {tune_err}")
            
    return summary_data

def handler(event, context):
    print("backtestValidator started")
    
    s3_bucket = os.environ.get('S3_BUCKET')
    outcomes_table_name = os.environ.get('DYNAMODB_TABLE_SCORE_OUTCOMES')
    scores_table_name = os.environ.get('DYNAMODB_TABLE_STOCK_SCORES')
    av_tier = os.environ.get('ALPHA_VANTAGE_TIER', 'premium')
    max_tickers = int(os.environ.get('MAX_TICKERS_TO_PROCESS', '20'))
    
    s3 = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    
    api_key = get_secret('/buffett-screener/alpha-vantage-key')
    if not api_key:
        print("AlphaVantage API key not found in secrets manager.")
        return {'status': 'FAILED', 'reason': 'NO_API_KEY'}
        
    outcomes_table = dynamodb.Table(outcomes_table_name)
    scores_table = dynamodb.Table(scores_table_name)
    
    # 1. Scan existing outcomes
    existing_outcomes = set()
    try:
        response = outcomes_table.scan(ProjectionExpression="runId, tickerHorizon")
        for item in response.get('Items', []):
            existing_outcomes.add((item['runId'], item['tickerHorizon']))
        while 'LastEvaluatedKey' in response:
            response = outcomes_table.scan(
                ProjectionExpression="runId, tickerHorizon",
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            for item in response.get('Items', []):
                existing_outcomes.add((item['runId'], item['tickerHorizon']))
    except Exception as e:
        print(f"Error scanning existing outcomes: {e}")
        
    # 2. Scan StockScores
    stock_scores = []
    try:
        response = scores_table.scan()
        stock_scores.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            response = scores_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            stock_scores.extend(response.get('Items', []))
    except Exception as e:
        print(f"Error scanning StockScores: {e}")
        
    # Build a lookup map of stock scores
    stock_scores_map = {(item['runId'], item['ticker']): item for item in stock_scores}
    
    # 3. Identify matured and unprocessed outcomes
    today = datetime.now(timezone.utc).date()
    horizons = [30, 90, 365]
    pending = []
    
    for item in stock_scores:
        created_at_str = item.get('createdAt')
        if not created_at_str:
            continue
            
        snapshot_date_str = created_at_str[:10] # YYYY-MM-DD
        try:
            snapshot_date = datetime.strptime(snapshot_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
            
        days_elapsed = (today - snapshot_date).days
        ticker = item['ticker']
        run_id = item['runId']
        
        for horizon in horizons:
            if days_elapsed >= horizon:
                ticker_horizon = f"{ticker}#{horizon}"
                if (run_id, ticker_horizon) not in existing_outcomes:
                    pending.append({
                        'runId': run_id,
                        'ticker': ticker,
                        'horizon': horizon,
                        'snapshot_date_str': snapshot_date_str,
                        'score_item': item
                    })
                    
    print(f"Total pending outcomes: {len(pending)}")
    
    if not pending:
        # Re-export stats anyway to keep it up to date
        all_outcomes = []
        try:
            res = outcomes_table.scan()
            all_outcomes.extend(res.get('Items', []))
            while 'LastEvaluatedKey' in res:
                res = outcomes_table.scan(ExclusiveStartKey=res['LastEvaluatedKey'])
                all_outcomes.extend(res.get('Items', []))
        except Exception as e:
            print(f"Error scanning outcomes for stats: {e}")
        export_validation_summary(s3, s3_bucket, all_outcomes, stock_scores_map)
        return {'status': 'SUCCESS', 'processed': 0}
        
    # Group pending by ticker to reuse API requests
    pending_by_ticker = {}
    for p in pending:
        pending_by_ticker.setdefault(p['ticker'], []).append(p)
        
    ticker_keys = list(pending_by_ticker.keys())[:max_tickers]
    print(f"Processing {len(ticker_keys)} tickers in this batch (limit {max_tickers})")
    
    # Fetch SPY first
    spy_series = _fetch_av_history('SPY', api_key)
    if not spy_series:
        print("Failed to fetch SPY historical data. Aborting.")
        return {'status': 'FAILED', 'reason': 'SPY_FETCH_FAILED'}
        
    sleep_time = 0.9 if av_tier == 'premium' else 15.0
    processed_count = 0
    
    for ticker in ticker_keys:
        ticker_series = _fetch_av_history(ticker, api_key)
        if not ticker_series:
            print(f"Skipping ticker {ticker} due to API fetch failure.")
            time.sleep(sleep_time)
            continue
            
        ticker_pendings = pending_by_ticker[ticker]
        for p in ticker_pendings:
            run_id = p['runId']
            horizon = p['horizon']
            snapshot_date_str = p['snapshot_date_str']
            
            # Target maturity date
            snapshot_dt = datetime.strptime(snapshot_date_str, "%Y-%m-%d").date()
            maturity_date_str = (snapshot_dt + timedelta(days=horizon)).strftime("%Y-%m-%d")
            
            # Get ticker prices
            price_snap, actual_snap_date = get_price_on_or_after(ticker_series, snapshot_date_str)
            price_mat, actual_mat_date = get_price_on_or_after(ticker_series, maturity_date_str)
            
            if price_snap is None or price_mat is None:
                print(f"Could not find historical price for {ticker} at snapshot {snapshot_date_str} or maturity {maturity_date_str}")
                continue
                
            # Get SPY prices at same dates
            spy_snap, _ = get_price_on_or_after(spy_series, snapshot_date_str)
            spy_mat, _ = get_price_on_or_after(spy_series, maturity_date_str)
            
            if spy_snap is None or spy_mat is None:
                print(f"Could not find SPY price for snapshot {snapshot_date_str} or maturity {maturity_date_str}")
                continue
                
            stock_return = round((price_mat - price_snap) / price_snap, 6)
            spy_return = round((spy_mat - spy_snap) / spy_snap, 6)
            excess_return = round(stock_return - spy_return, 6)
            
            # Write to DynamoDB
            outcome_item = {
                'runId': run_id,
                'tickerHorizon': f"{ticker}#{horizon}",
                'ticker': ticker,
                'horizonDays': horizon,
                'scoreSnapshotDate': snapshot_date_str,
                'stockReturnPct': decimal.Decimal(str(stock_return)),
                'spReturnPct': decimal.Decimal(str(spy_return)),
                'excessReturnPct': decimal.Decimal(str(excess_return)),
                'computedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            }
            
            try:
                outcomes_table.put_item(Item=outcome_item)
                processed_count += 1
            except Exception as e:
                print(f"Failed to write outcome to DynamoDB for {ticker} (horizon {horizon}): {e}")
                
        time.sleep(sleep_time)
        
    # Re-fetch all outcomes and export validation summary to S3
    all_outcomes = []
    try:
        res = outcomes_table.scan()
        all_outcomes.extend(res.get('Items', []))
        while 'LastEvaluatedKey' in res:
            res = outcomes_table.scan(ExclusiveStartKey=res['LastEvaluatedKey'])
            all_outcomes.extend(res.get('Items', []))
    except Exception as e:
        print(f"Error scanning outcomes for final export: {e}")
        
    export_validation_summary(s3, s3_bucket, all_outcomes, stock_scores_map)
    
    return {
        'status': 'SUCCESS',
        'processed': processed_count
    }
