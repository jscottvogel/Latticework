import json
import os
import boto3
import random
import time
from datetime import datetime, timezone

# UNCERTAINTY RANGES
UNCERTAINTY = {
    'roe5yrAvg':      0.15,
    'netMargin':      0.20,
    'debtToEquity':   0.10,
    'fcfGrowth3yr':   0.25,
    'epsGrowth5yr':   0.25,
    'currentRatio':   0.05,
    'peRatio':        0.20,
}

# THRESHOLDS
MIN_ROE = 0.15
MIN_NET_MARGIN = 0.10
MAX_DEBT_TO_EQUITY = 0.75
MIN_FCF_GROWTH = 0.05
MIN_EPS_GROWTH = 0.08
MIN_CURRENT_RATIO = 1.2
MAX_PE_RATIO = 35

def quant_score(metrics):
    score = 0
    
    roe = metrics.get('roe5yrAvg')
    if roe is not None and roe >= MIN_ROE: score += 25
    
    nm = metrics.get('netMargin')
    if nm is not None and nm >= MIN_NET_MARGIN: score += 20
    
    de = metrics.get('debtToEquity')
    if de is not None and de <= MAX_DEBT_TO_EQUITY: score += 15
    
    fcf = metrics.get('fcfGrowth3yr')
    if fcf is not None and fcf >= MIN_FCF_GROWTH: score += 15
    
    eps = metrics.get('epsGrowth5yr')
    if eps is not None and eps >= MIN_EPS_GROWTH: score += 15
    
    cr = metrics.get('currentRatio')
    if cr is not None and cr >= MIN_CURRENT_RATIO: score += 5
    
    pe = metrics.get('peRatio')
    if pe is not None and pe > 0 and pe <= MAX_PE_RATIO: score += 5
    
    return float(score) # 0 to 100

def _safe_float(val):
    try:
        if val is None: return None
        return float(val)
    except:
        return None

def run_simulation(raw_metrics, n_runs=500):
    scores = []
    
    metrics = {k: _safe_float(v) for k, v in raw_metrics.items()}
    
    for i in range(n_runs):
        sampled = dict(metrics) # copy
        
        for metric, pct in UNCERTAINTY.items():
            actual = sampled.get(metric)
            if actual is not None:
                std = abs(actual) * pct
                val = random.gauss(actual, std)
                
                # Clip bounds
                if metric == 'roe5yrAvg': val = max(-0.5, min(1.0, val))
                elif metric == 'netMargin': val = max(-1.0, min(1.0, val))
                elif metric == 'debtToEquity': val = max(0.0, min(10.0, val))
                elif metric == 'fcfGrowth3yr': val = max(-0.5, min(2.0, val))
                elif metric == 'epsGrowth5yr': val = max(-0.5, min(2.0, val))
                elif metric == 'currentRatio': val = max(0.1, min(10.0, val))
                elif metric == 'peRatio': val = max(1.0, min(100.0, val))
                
                sampled[metric] = val
                
        scores.append(quant_score(sampled))
        
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    
    p10 = sorted_scores[int(n * 0.10)]
    p25 = sorted_scores[int(n * 0.25)]
    p75 = sorted_scores[int(n * 0.75)]
    p90 = sorted_scores[int(n * 0.90)]
    
    mean = sum(scores) / n
    std_dev = (sum((x - mean)**2 for x in scores) / n) ** 0.5
    prob_investigate = sum(1 for s in scores if s > 70) / n
    
    if std_dev < 8:
        band = 'TIGHT'
    elif std_dev < 15:
        band = 'MODERATE'
    else:
        band = 'WIDE'
        
    return {
        'n_runs': n_runs,
        'mean_score': mean,
        'median_score': sorted_scores[n // 2],
        'std_dev': std_dev,
        'p10': p10,
        'p25': p25,
        'p75': p75,
        'p90': p90,
        'prob_investigate': prob_investigate,
        'confidence_band': band
    }

def handler(event, context):
    start_t = time.time()
    print("monteCarlo started")
    
    candidates = event.get('scored_candidates', event.get('candidates', []))
    run_id = event.get('run_id', 'UNKNOWN')
    
    results = {}
    
    for candidate in candidates:
        ticker = candidate.get('ticker')
        # Some payloads might pass nested 'metrics', others flat. Handle both.
        raw = candidate.get('metrics', candidate)
        res = run_simulation(raw)
        res['ticker'] = ticker
        results[ticker] = res
        
    elapsed = time.time() - start_t
    print(f"500 runs x {len(candidates)} stocks completed in {elapsed:.1f}s")
    
    # Update DynamoDB StockScores
    db_table = os.environ.get('DYNAMODB_TABLE_STOCK_SCORES')
    if db_table and candidates:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(db_table)
        
        for ticker, res in results.items():
            try:
                # Update item using expression to only touch the new fields
                table.update_item(
                    Key={
                        'runId': run_id,
                        'ticker': ticker
                    },
                    UpdateExpression="SET mcP10 = :p10, mcP90 = :p90, mcProbInvestigate = :prob, mcConfidenceBand = :band",
                    ExpressionAttributeValues={
                        ':p10': str(res['p10']),
                        ':p90': str(res['p90']),
                        ':prob': str(res['prob_investigate']),
                        ':band': res['confidence_band']
                    }
                )
            except Exception as e:
                print(f"DynamoDB update failed for {ticker}: {e}")

    # No further lambdas to trigger, pipeline complete.
    print("Pipeline complete.")

    return {
        'results': results
    }
