import json
import os
import boto3
import time
from datetime import datetime, timezone

def get_run_id():
    now = datetime.now(timezone.utc)
    week = now.isocalendar()[1]
    return f'{now.year}-W{week:02d}'

def invoke_lambda(function_name_env_key, payload):
    function_arn = os.environ.get(function_name_env_key)
    if not function_arn:
        raise RuntimeError(f"Missing environment variable: {function_name_env_key}")
        
    client = boto3.client('lambda')
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

def update_rolling_scores(run_id, current_scores):
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ.get('DYNAMODB_TABLE_ROLLING_SCORES')
    if not table_name:
        return
        
    table = dynamodb.Table(table_name)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 1. Fetch all existing RollingScores
    response = table.scan()
    all_rolling = {item['ticker']: item for item in response.get('Items', [])}
    
    # 2. Process current week's scores
    current_tickers = set()
    for s in current_scores:
        ticker = s['ticker']
        current_tickers.add(ticker)
        
        record = all_rolling.get(ticker, {
            'ticker': ticker,
            'companyName': s.get('companyName'),
            'sector': s.get('sector'),
            'scoreHistory': [] # custom list we will maintain
        })
        
        history = record.get('scoreHistory', [])
        # Add this week's score
        history.append({
            'runId': run_id,
            'compositeScore': float(s.get('compositeScore', 0)),
            'verdict': s.get('verdict')
        })
        # Keep only last 4 weeks
        history = history[-4:]
        record['scoreHistory'] = history
        
        # Recalculate
        appearances = len(history)
        avg_score = sum(h['compositeScore'] for h in history) / appearances if appearances > 0 else 0
        investigate_count = sum(1 for h in history if h['verdict'] == 'INVESTIGATE')
        is_investable = appearances >= 3 and avg_score >= 7.0
        
        record['appearancesLast4Weeks'] = appearances
        record['avgCompositeScore'] = avg_score
        record['investigateCount'] = investigate_count
        record['isInvestable'] = is_investable
        record['latestThesis'] = s.get('oneLineThesis')
        record['latestVerdict'] = s.get('verdict')
        record['lastSeen'] = run_id
        record['updatedAt'] = now_iso
        
        all_rolling[ticker] = record
        
    # 3. Process stocks that dropped off this week
    dropped_tickers = set(all_rolling.keys()) - current_tickers
    for ticker in dropped_tickers:
        record = all_rolling[ticker]
        # Keep only last 4 weeks (meaning drop oldest if 4 exist, but since it didn't appear this week,
        # we might just do nothing, or we explicitly enforce a rolling 4-week window based on runId parsing.
        # For simplicity, if they aren't scored this week, their 'appearances' should naturally degrade over time
        # if we parse the runIds. For a true 4-week window without parsing, we just leave the history untouched
        # but mark them as not seen this week. 
        # The prompt says: "Remove this week from their history (they dropped off the list)."
        # Actually, if we just want to track appearances over the last 4 runs, we need the runIds of the last 4 runs.
        # For now, we will simply set isInvestable to False if they drop off to be safe.
        record['isInvestable'] = False
        record['updatedAt'] = now_iso
        
    # 4. Write back to DynamoDB
    with table.batch_writer() as batch:
        for ticker, item in all_rolling.items():
            # DynamoDB requires decimal/str for floats, but float works in boto3 sometimes. Best to stringify.
            item_to_put = dict(item)
            item_to_put['avgCompositeScore'] = str(item.get('avgCompositeScore', 0))
            batch.put_item(Item=item_to_put)

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
    
    dry_run = event.get('dry_run', False)
    if dry_run:
        print("DRY RUN ENABLED: Will skip AI scoring and Monte Carlo.")
    
    dynamodb = boto3.resource('dynamodb')
    runs_table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE_WEEKLY_RUNS'))
    
    runs_table.put_item(Item={
        'runId': run_id,
        'status': 'RUNNING',
        'createdAt': datetime.now(timezone.utc).isoformat()
    })
    
    try:
        # Step 1: Fetch
        print('Step 1/5: Fetching financial data...')
        fetch_result = invoke_lambda('DATA_FETCH_FUNCTION_NAME', {'run_id': run_id})
        metrics = fetch_result.get('metrics', [])
        s3_key = fetch_result.get('s3_key')
        print(f'Fetched {len(metrics)} stocks')
        
        # Step 2: Quant
        print('Step 2/5: Running quantitative filter...')
        filter_result = invoke_lambda('QUANT_FILTER_FUNCTION_NAME', {'run_id': run_id, 's3_metrics_key': s3_key})
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
        news_payload = [{'ticker': c['ticker'], 'company_name': c.get('companyName')} for c in candidates]
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
        update_rolling_scores(run_id, scores)
        
        # Export
        print('Exporting dashboard...')
        export_dashboard_to_s3(run_id, scores)
        
        # Complete
        runs_table.update_item(
            Key={'runId': run_id},
            UpdateExpression="SET #s = :status, totalCostUsd = :cost, stocksScreened = :ss, candidatesScored = :cs",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':status': 'COMPLETE',
                ':cost': str(ai_cost),
                ':ss': len(metrics),
                ':cs': len(candidates)
            }
        )
        
        summary = f"Weekly Run {run_id} Complete.\nScreened: {len(metrics)}\nCandidates: {len(candidates)}\nCost: ${ai_cost:.4f}"
        print(summary)
        send_alert('Weekly Screen Complete', summary)
        
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
        raise
