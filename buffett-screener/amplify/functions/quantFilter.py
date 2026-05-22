import json
import os
import boto3

# THRESHOLDS
MIN_ROE = 0.15
MIN_NET_MARGIN = 0.10
MAX_DEBT_TO_EQUITY = 0.75
MIN_FCF_GROWTH = 0.05
MIN_EPS_GROWTH = 0.08
MIN_CURRENT_RATIO = 1.2
MAX_PE_RATIO = 35
MAX_CANDIDATES = 20

def score_stock(metrics):
    score = 0
    flags_passed = []
    flags_failed = []

    def check(condition, pts, name):
        nonlocal score
        if condition:
            score += pts
            flags_passed.append(name)
        else:
            flags_failed.append(name)

    roe = metrics.get('roe5yrAvg')
    check(roe is not None and roe >= MIN_ROE, 25, 'ROE >= 15%')

    nm = metrics.get('netMargin')
    check(nm is not None and nm >= MIN_NET_MARGIN, 20, 'Net Margin >= 10%')

    de = metrics.get('debtToEquity')
    check(de is not None and de <= MAX_DEBT_TO_EQUITY, 15, 'D/E <= 0.75')

    fcf = metrics.get('fcfGrowth3yr')
    check(fcf is not None and fcf >= MIN_FCF_GROWTH, 15, 'FCF Growth >= 5%')

    eps = metrics.get('epsGrowth5yr')
    check(eps is not None and eps >= MIN_EPS_GROWTH, 15, 'EPS Growth >= 8%')

    cr = metrics.get('currentRatio')
    check(cr is not None and cr >= MIN_CURRENT_RATIO, 5, 'Current Ratio >= 1.2')

    pe = metrics.get('peRatio')
    check(pe is not None and pe > 0 and pe <= MAX_PE_RATIO, 5, 'PE <= 35')

    passes = score >= 50

    return {
        'passes': passes,
        'score': score,
        'flags_passed': flags_passed,
        'flags_failed': flags_failed
    }

def filter_candidates(all_metrics, previous_top_tickers=[]):
    results = []
    for metrics in all_metrics:
        evaluation = score_stock(metrics)
        ticker = metrics.get('ticker')
        is_previous_winner = ticker in previous_top_tickers
        
        if evaluation['passes'] or is_previous_winner:
            results.append({
                'ticker': ticker,
                'metrics': metrics,
                'quant_score': evaluation['score'],
                'flags_passed': evaluation['flags_passed'],
                'flags_failed': evaluation['flags_failed']
            })

    # Sort by score descending
    results.sort(key=lambda x: x['quant_score'], reverse=True)
    
    passed_count = len(results)
    returned = results[:MAX_CANDIDATES]
    
    print(f"Quant filter: {len(all_metrics)} tickers -> {passed_count} passed -> {len(returned)} returned")
    return returned

def handler(event, context):
    print("quantFilter started")
    
    run_id = event.get('run_id')
    s3_metrics_key = event.get('s3_metrics_key')
    
    if not s3_metrics_key:
        print("No s3_metrics_key provided. Exiting.")
        return {'candidates': []}
        
    s3_bucket = os.environ.get('S3_BUCKET')
    s3 = boto3.client('s3')
    
    try:
        obj = s3.get_object(Bucket=s3_bucket, Key=s3_metrics_key)
        all_metrics = json.loads(obj['Body'].read().decode('utf-8'))
    except Exception as e:
        print(f"Failed to read metrics from S3: {e}")
        return {'candidates': []}
        
    previous_top_tickers = event.get('previous_top_tickers', [])
    candidates = filter_candidates(all_metrics, previous_top_tickers)
    
    # Save candidates to DynamoDB (StockScores table) if needed, 
    # or pass them to the next Lambda (aiScorer).
    db_table = os.environ.get('DYNAMODB_TABLE_STOCK_SCORES')
    if db_table and candidates:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(db_table)
        for c in candidates:
            # DynamoDB requires decimals/strings for floats
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            item = {
                'runId': run_id,
                'ticker': c['ticker'],
                'compositeScore': str(c['quant_score']),
                '__typename': 'StockScore',
                'createdAt': now_iso,
                'updatedAt': now_iso
            }
            try:
                table.put_item(Item=item)
            except Exception as e:
                print(f"DynamoDB write failed for {c['ticker']}: {e}")

    return {
        'candidates': candidates
    }
