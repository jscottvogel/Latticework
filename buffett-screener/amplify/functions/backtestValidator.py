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

def export_validation_summary(s3_client, s3_bucket, outcomes, stock_scores_map):
    horizons = [30, 90, 365]
    summary_data = {
        "updatedAt": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "horizons": {}
    }
    
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
            
        summary_data["horizons"][str(horizon)] = {
            "count": len(horizon_outcomes),
            "correlations": correlations,
            "calibration": {
                "investigateHighCount": investigate_high_count,
                "investigateHighBeatCount": investigate_high_beat_count,
                "investigateHighBeatRate": beat_rate
            },
            "tiers": tier_data
        }
        
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
