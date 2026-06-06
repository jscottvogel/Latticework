import json
import os
import boto3
from botocore.config import Config
import time
from datetime import datetime, timezone, timedelta

def get_run_id():
    now = datetime.now(timezone.utc)
    day_of_year = now.timetuple().tm_yday
    return f'{now.year}-D{day_of_year:03d}'

def is_us_holiday_or_weekend(dt):
    # 0 = Monday, 6 = Sunday
    if dt.weekday() in (5, 6):
        return True
        
    year = dt.year
    month = dt.month
    day = dt.day

    def get_nth_weekday(year, month, weekday, n):
        if n > 0:
            count = 0
            for d in range(1, 32):
                try:
                    curr = datetime(year, month, d)
                    if curr.weekday() == weekday:
                        count += 1
                        if count == n:
                            return d
                except ValueError:
                    break
        else:
            for d in range(31, 0, -1):
                try:
                    curr = datetime(year, month, d)
                    if curr.weekday() == weekday:
                        return d
                except ValueError:
                    pass
        return None

    holidays = set()
    
    # New Year's Day
    jan1 = datetime(year, 1, 1)
    if jan1.weekday() == 6:
        holidays.add((year, 1, 2))
    else:
        holidays.add((year, 1, 1))
        
    # MLK Day: 3rd Monday in Jan
    holidays.add((year, 1, get_nth_weekday(year, 1, 0, 3)))
    
    # Presidents' Day: 3rd Monday in Feb
    holidays.add((year, 2, get_nth_weekday(year, 2, 0, 3)))
    
    # Good Friday
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month_easter = (h + l - 7 * m + 114) // 31
    day_easter = ((h + l - 7 * m + 114) % 31) + 1
    easter = datetime(year, month_easter, day_easter)
    good_friday = easter - timedelta(days=2)
    holidays.add((year, good_friday.month, good_friday.day))
    
    # Memorial Day: last Monday in May
    holidays.add((year, 5, get_nth_weekday(year, 5, 0, -1)))
    
    # Juneteenth: June 19
    j19 = datetime(year, 6, 19)
    if j19.weekday() == 5:
        holidays.add((year, 6, 18))
    elif j19.weekday() == 6:
        holidays.add((year, 6, 20))
    else:
        holidays.add((year, 6, 19))
        
    # Independence Day: July 4
    jul4 = datetime(year, 7, 4)
    if jul4.weekday() == 5:
        holidays.add((year, 7, 3))
    elif jul4.weekday() == 6:
        holidays.add((year, 7, 5))
    else:
        holidays.add((year, 7, 4))
        
    # Labor Day: 1st Monday in Sep
    holidays.add((year, 9, get_nth_weekday(year, 9, 0, 1)))
    
    # Thanksgiving: 4th Thursday in Nov
    holidays.add((year, 11, get_nth_weekday(year, 11, 3, 4)))
    
    # Christmas: Dec 25
    dec25 = datetime(year, 12, 25)
    if dec25.weekday() == 5:
        holidays.add((year, 12, 24))
    elif dec25.weekday() == 6:
        holidays.add((year, 12, 26))
    else:
        holidays.add((year, 12, 25))
        
    return (year, month, day) in holidays

def invoke_lambda(function_name_env_key, payload):
    function_arn = os.environ.get(function_name_env_key)
    if not function_arn:
        raise RuntimeError(f"Missing environment variable: {function_name_env_key}")
        
    config = Config(read_timeout=900, connect_timeout=60, retries={'max_attempts': 0})
    client = boto3.client('lambda', config=config)
    print(f"Invoking {function_arn} synchronously...")
    start_t = time.time()
    
    response = client.invoke(
        FunctionName=function_arn,
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    elapsed = time.time() - start_t
    print(f"Invocation completed in {elapsed:.1f}s")
    
    if 'FunctionError' in response:
        error_msg = response['Payload'].read().decode('utf-8')
        raise RuntimeError(f"Lambda {function_arn} failed: {error_msg}")
        
    return json.loads(response['Payload'].read().decode('utf-8'))

def send_alert(subject, message):
    sns_arn = os.environ.get('SNS_ALERT_ARN')
    if sns_arn:
        sns = boto3.client('sns')
        try:
            sns.publish(
                TopicArn=sns_arn,
                Subject=subject,
                Message=message
            )
            print("Alert sent via SNS.")
        except Exception as e:
            print(f"Failed to send SNS alert: {e}")

def update_rolling_scores(run_id, current_scores, candidates=None):
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ.get('DYNAMODB_TABLE_ROLLING_SCORES')
    if not table_name:
        return
        
    table = dynamodb.Table(table_name)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Normalize current_scores to camelCase
    candidate_map = {}
    if candidates:
        candidate_map = {c['ticker']: c for c in candidates}
        
    normalized_scores = []
    for s in current_scores:
        ticker = s['ticker']
        cand = candidate_map.get(ticker, {})
        metrics = cand.get('metrics', {})
        
        normalized = {
            'ticker': ticker,
            'companyName': s.get('company_name') or metrics.get('name') or cand.get('companyName') or s.get('companyName'),
            'sector': metrics.get('sector') or cand.get('sector') or s.get('sector'),
            'compositeScore': s.get('composite_score') or s.get('compositeScore') or 0,
            'verdict': s.get('verdict'),
            'oneLineThesis': s.get('one_line_thesis') or s.get('oneLineThesis') or 'No thesis.',
            'rankThisWeek': s.get('rank_this_week') or s.get('rankThisWeek')
        }
        normalized_scores.append(normalized)
        
    # Fetch completed runs
    runs_table_name = os.environ.get('DYNAMODB_TABLE_WEEKLY_RUNS')
    runs_table = dynamodb.Table(runs_table_name)
    runs_response = runs_table.scan(
        FilterExpression="#s = :status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":status": "COMPLETE"}
    )
    completed_runs = runs_response.get('Items', [])
    completed_runs.sort(key=lambda x: x.get('createdAt', x.get('runDate', '')), reverse=True)
    
    # Get last 28 runs: current run plus the last 27 completed runs
    recent_run_ids = [run_id]
    for r in completed_runs:
        if r['runId'] != run_id:
            recent_run_ids.append(r['runId'])
            if len(recent_run_ids) == 28:
                break
                
    scores_table_name = os.environ.get('DYNAMODB_TABLE_STOCK_SCORES')
    scores_table = dynamodb.Table(scores_table_name)
    
    # Map runId -> ticker -> score_item
    scores_by_run_and_ticker = {}
    scores_by_run_and_ticker[run_id] = {s['ticker']: s for s in normalized_scores}
    
    ticker_metadata = {}
    for s in normalized_scores:
        ticker = s['ticker']
        ticker_metadata[ticker] = {
            'companyName': s.get('companyName'),
            'sector': s.get('sector'),
            'latestThesis': s.get('oneLineThesis'),
            'latestVerdict': s.get('verdict'),
            'lastSeen': run_id,
            'compositeScore': float(s.get('compositeScore', 0))
        }
        
    for rid in recent_run_ids:
        if rid == run_id:
            continue
        try:
            res = scores_table.query(
                KeyConditionExpression="runId = :rid",
                ExpressionAttributeValues={":rid": rid}
            )
            run_scores = res.get('Items', [])
            if not run_scores:
                continue
                
            # Normalize to camelCase
            norm_run_scores = []
            for s in run_scores:
                norm_run_scores.append({
                    'ticker': s['ticker'],
                    'companyName': s.get('companyName') or s.get('company_name'),
                    'sector': s.get('sector'),
                    'compositeScore': float(s.get('compositeScore') or s.get('composite_score') or 0),
                    'verdict': s.get('verdict'),
                    'oneLineThesis': s.get('oneLineThesis') or s.get('one_line_thesis') or 'No thesis.',
                    'rankThisWeek': s.get('rankThisWeek') or s.get('rank_this_week')
                })
                
            scores_by_run_and_ticker[rid] = {s['ticker']: s for s in norm_run_scores}
            
            for s in norm_run_scores:
                ticker = s['ticker']
                if ticker not in ticker_metadata:
                    ticker_metadata[ticker] = {
                        'companyName': s.get('companyName'),
                        'sector': s.get('sector'),
                        'latestThesis': s.get('oneLineThesis'),
                        'latestVerdict': s.get('verdict'),
                        'lastSeen': rid,
                        'compositeScore': s.get('compositeScore')
                    }
        except Exception as e:
            print(f"Warning: Failed to fetch scores for run {rid}: {e}")
            
    # Calculate top 10 for each run
    top_10_by_run = {}
    for rid, ticker_map in scores_by_run_and_ticker.items():
        sorted_tickers = sorted(ticker_map.keys(), key=lambda t: float(ticker_map[t].get('compositeScore', 0)), reverse=True)
        top_10_by_run[rid] = set(sorted_tickers[:10])
        
    # Fetch existing RollingScores
    response = table.scan()
    all_rolling = {item['ticker']: item for item in response.get('Items', [])}
    
    all_tickers = set(all_rolling.keys()) | set(ticker_metadata.keys())
    
    import decimal
    with table.batch_writer() as batch:
        for ticker in all_tickers:
            history = []
            appearances = 0
            investigate_count = 0
            scores_for_avg = []
            
            for rid in reversed(recent_run_ids):
                run_data = scores_by_run_and_ticker.get(rid, {})
                if ticker in run_data:
                    s = run_data[ticker]
                    comp_score = float(s.get('compositeScore', 0))
                    verdict = s.get('verdict')
                    
                    if ticker in top_10_by_run.get(rid, set()):
                        appearances += 1
                        
                    if verdict == 'INVESTIGATE':
                        investigate_count += 1
                        
                    scores_for_avg.append(comp_score)
                    history.append({
                        'runId': rid,
                        'compositeScore': decimal.Decimal(str(comp_score)),
                        'verdict': verdict
                    })
                    
            # Keep history to last 28 runs
            history = history[-28:]
            
            # Recalculate
            avg_score = sum(scores_for_avg) / len(scores_for_avg) if scores_for_avg else 0.0
            is_investable = appearances >= 28
            
            meta = ticker_metadata.get(ticker, {})
            existing = all_rolling.get(ticker, {})
            
            company_name = meta.get('companyName') or existing.get('companyName')
            sector = meta.get('sector') or existing.get('sector')
            latest_thesis = meta.get('latestThesis') or existing.get('latestThesis')
            latest_verdict = meta.get('latestVerdict') or existing.get('latestVerdict')
            last_seen = meta.get('lastSeen') or existing.get('lastSeen')
            
            record = {
                'ticker': ticker,
                'companyName': company_name,
                'sector': sector,
                'scoreHistory': history,
                'appearancesLast4Weeks': appearances,
                'avgCompositeScore': decimal.Decimal(str(avg_score)),
                'investigateCount': investigate_count,
                'isInvestable': is_investable,
                'latestThesis': latest_thesis,
                'latestVerdict': latest_verdict,
                'lastSeen': last_seen,
                'updatedAt': now_iso,
                '__typename': 'RollingScore'
            }
            
            if ticker in all_rolling:
                record['createdAt'] = all_rolling[ticker].get('createdAt', now_iso)
            else:
                record['createdAt'] = now_iso
                
            batch.put_item(Item=record)


def export_dashboard_to_s3(run_id, top_scores):
    s3 = boto3.client('s3')
    bucket = os.environ.get('S3_BUCKET')
    if not bucket:
        return
        
    dynamodb = boto3.resource('dynamodb')
    
    # Get rolling investable
    rolling_table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE_ROLLING_SCORES'))
    rolling_res = rolling_table.scan(
        FilterExpression='isInvestable = :val',
        ExpressionAttributeValues={':val': True}
    )
    investable = rolling_res.get('Items', [])
    
    dashboard = {
        'runId': run_id,
        'updatedAt': datetime.now(timezone.utc).isoformat(),
        'topScores': top_scores[:20],
        'investable': investable
    }
    
    payload = json.dumps(dashboard, default=str)
    
    try:
        s3.put_object(Bucket=bucket, Key=f'dashboard/latest.json', Body=payload)
        s3.put_object(Bucket=bucket, Key=f'dashboard/{run_id}.json', Body=payload)
        print("Dashboard exported to S3.")
    except Exception as e:
        print(f"Failed to export dashboard: {e}")

def handler(event, context):
    run_id = get_run_id()
    print(f'Starting weekly screen: {run_id}')
    
    force = event.get('force', False)
    cst_now = datetime.now(timezone.utc) - timedelta(hours=6)
    if not force and is_us_holiday_or_weekend(cst_now):
        print(f"Skipping run {run_id} because today ({cst_now.strftime('%Y-%m-%d')}) is a weekend or US federal holiday. Use 'force': true to override.")
        try:
            dynamodb = boto3.resource('dynamodb')
            runs_table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE_WEEKLY_RUNS'))
            now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            runs_table.put_item(Item={
                'runId': run_id,
                'runDate': cst_now.strftime('%Y-%m-%d'),
                'status': 'SKIPPED',
                'errorMessage': 'Skipped due to US holiday or weekend',
                'createdAt': now_iso,
                'updatedAt': now_iso,
                '__typename': 'WeeklyRun'
            })
        except Exception as e:
            print(f"Failed to write skipped state to DynamoDB: {e}")
        return {'status': 'SKIPPED_HOLIDAY_OR_WEEKEND'}

    
    dry_run = event.get('dry_run', False)
    if dry_run:
        print("DRY RUN ENABLED: Will skip AI scoring and Monte Carlo.")
    
    dynamodb = boto3.resource('dynamodb')
    runs_table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE_WEEKLY_RUNS'))
    
    # Determine previous top 10 tickers from LAST WEEK (exclude current week)
    previous_top_tickers = []
    try:
        scores_table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE_STOCK_SCORES'))
        response = runs_table.scan(
            FilterExpression="#s = :status",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": "COMPLETE"}
        )
        completed_runs = response.get('Items', [])
        
        # Exclude any runs from the current week to force it to look at last week
        completed_runs = [r for r in completed_runs if r['runId'] != run_id]
        
        if completed_runs:
            completed_runs.sort(key=lambda x: x.get('createdAt', x.get('runDate', '')), reverse=True)
            last_run_id = completed_runs[0]['runId']
            
            res = scores_table.query(
                KeyConditionExpression="runId = :rid",
                ExpressionAttributeValues={":rid": last_run_id}
            )
            last_scores = res.get('Items', [])
            last_scores.sort(key=lambda x: float(x.get('compositeScore', 0)), reverse=True)
            previous_top_tickers = [s['ticker'] for s in last_scores]
            print(f"Carrying over all {len(previous_top_tickers)} screened tickers from run {last_run_id}: {previous_top_tickers}")
    except Exception as e:
        print(f"Warning: Failed to fetch previous top tickers: {e}")
        
    now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    runs_table.put_item(Item={
        'runId': run_id,
        'runDate': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'status': 'RUNNING',
        'createdAt': now_iso,
        'updatedAt': now_iso,
        '__typename': 'WeeklyRun'
    })
    
    try:
        # Step 1: Fetch
        print('Step 1/5: Fetching financial data...')

        fetch_result = invoke_lambda('DATA_FETCH_FUNCTION_NAME', {
            'run_id': run_id, 
            'previous_top_tickers': previous_top_tickers
        })
        metrics = fetch_result.get('metrics', [])
        s3_key = fetch_result.get('s3_key')
        print(f'Fetched {len(metrics)} stocks')
        
        # Step 2: Quant
        print('Step 2/5: Running quantitative filter...')
        filter_result = invoke_lambda('QUANT_FILTER_FUNCTION_NAME', {
            'run_id': run_id, 
            's3_metrics_key': s3_key,
            'previous_top_tickers': previous_top_tickers
        })
        candidates = filter_result.get('candidates', [])
        print(f'Quant filter: {len(metrics)} -> {len(candidates)} candidates')
        
        if dry_run:
            print("DRY RUN: skipping news collection, AI scoring, and Monte Carlo.")
            runs_table.update_item(
                Key={'runId': run_id},
                UpdateExpression="SET #s = :status, errorMessage = :msg",
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':status': 'COMPLETE', ':msg': 'DRY RUN'}
            )
            return {'status': 'DRY_RUN_COMPLETE'}

        # Step 3: News
        print('Step 3/5: Collecting news...')
        news_payload = [{'ticker': c['ticker'], 'company_name': c.get('metrics', {}).get('name') or c.get('companyName')} for c in candidates]
        news_result = invoke_lambda('NEWS_FETCH_FUNCTION_NAME', {'run_id': run_id, 'candidates': news_payload})
        news = news_result.get('news', {})
        
        # Merge news
        for c in candidates:
            c['news_summary'] = news.get(c['ticker'], 'No recent news.')

        # Step 4: AI
        print('Step 4/5: AI scoring with Claude Haiku...')
        score_result = invoke_lambda('AI_SCORER_FUNCTION_NAME', {
            'run_id': run_id,
            'candidates': candidates
        })
        scores = score_result.get('scores', [])
        ai_cost = score_result.get('total_cost_usd', 0.0)
        print(f'AI scoring complete. Cost: ${ai_cost:.4f}')

        # Step 5: Monte Carlo
        print('Step 5/5: Running Monte Carlo simulation...')
        invoke_lambda('MONTE_CARLO_FUNCTION_NAME', {
            'run_id': run_id,
            'candidates': scores
        })
        
        # Update rolling
        print('Updating rolling scores...')
        update_rolling_scores(run_id, scores, candidates)
        
        # Export
        print('Exporting dashboard...')
        export_dashboard_to_s3(run_id, scores)
        
        # Complete
        import decimal
        runs_table.update_item(
            Key={'runId': run_id},
            UpdateExpression="SET #s = :status, totalCostUsd = :cost, stocksScreened = :ss, candidatesScored = :cs, updatedAt = :updated",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':status': 'COMPLETE',
                ':cost': decimal.Decimal(str(ai_cost)),
                ':ss': len(metrics),
                ':cs': len(candidates),
                ':updated': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            }
        )
        
        summary = f"Weekly Run {run_id} Complete.\nScreened: {len(metrics)}\nCandidates: {len(candidates)}\nCost: ${ai_cost:.4f}"
        print(summary)
        send_alert('Weekly Screen Complete', summary)
        
        if 'requestContext' in event:
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({'status': 'COMPLETE', 'run_id': run_id})
            }
        return {'status': 'COMPLETE', 'run_id': run_id}
        
    except Exception as e:
        print(f'Run {run_id} FAILED: {str(e)}')
        runs_table.update_item(
            Key={'runId': run_id},
            UpdateExpression="SET #s = :status, errorMessage = :err",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':status': 'FAILED',
                ':err': str(e)
            }
        )
        send_alert(f'ALERT: Weekly Screen Failed ({run_id})', str(e))
        
        if 'requestContext' in event:
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({'error': str(e), 'failed': True})
            }
        raise
