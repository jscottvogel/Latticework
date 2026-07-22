import json
import os
import boto3
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone

_ANTHROPIC_KEY = None

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
        except (json.JSONDecodeError, TypeError):
            match = re.search(r'[\'"]?(?:key|apikey|apiKey)[\'"]?\s*[:=]\s*[\'"]?([A-Za-z0-9\-]+)[\'"]?', secret_string)
            if match:
                _ANTHROPIC_KEY = match.group(1)
            else:
                _ANTHROPIC_KEY = secret_string.strip('\'"{} ')
        return _ANTHROPIC_KEY
    except Exception as e:
        print(f"Error fetching Anthropic secret: {e}")
        return None

def _call_anthropic_api(api_key, user_msg):
    url = "https://api.anthropic.com/v1/messages"
    sys_prompt = "You are a professional buy-side research analyst writing a deep-dive, institutional-grade Buffett-style investment memo."
    
    payload = {
        "model": "claude-haiku-4-5-20251001", # actively supported Haiku 4.5 model
        "max_tokens": 4000,
        "system": sys_prompt,
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

def handler(event, context):
    print("memoGenerator started")
    ticker = event.get('ticker')
    run_id = event.get('run_id')
    
    if not ticker or not run_id:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing ticker or run_id'})
        }
        
    dynamodb = boto3.resource('dynamodb')
    s3_client = boto3.client('s3')
    
    scores_table_name = os.environ.get('DYNAMODB_TABLE_STOCK_SCORES')
    financials_table_name = os.environ.get('DYNAMODB_TABLE_RAW_FINANCIALS')
    s3_bucket = os.environ.get('S3_BUCKET')
    
    # 1. Fetch score details
    score_details = {}
    if scores_table_name:
        try:
            table = dynamodb.Table(scores_table_name)
            response = table.get_item(Key={'runId': run_id, 'ticker': ticker})
            score_details = response.get('Item', {})
        except Exception as e:
            print(f"Error reading stock score: {e}")
            
    # 2. Fetch raw financials overview
    financials = {}
    if financials_table_name:
        try:
            table = dynamodb.Table(financials_table_name)
            # PartitionKey is ticker, SortKey is runId
            response = table.get_item(Key={'ticker': ticker, 'runId': run_id})
            financials = response.get('Item', {})
        except Exception as e:
            print(f"Error reading raw financials: {e}")
            
    if not score_details:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': f'StockScore details not found for {ticker} (run {run_id})'})
        }
        
    api_key = get_anthropic_key()
    if not api_key:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Anthropic API key not found.'})
        }
        
    company_name = score_details.get('companyName', ticker)
    sector = score_details.get('sector', 'N/A')
    description = financials.get('description', 'No overview description available.')
    
    # Extract sub-scores
    moat = score_details.get('scoreMoat')
    fin_health = score_details.get('scoreFinancialHealth')
    management = score_details.get('scoreManagement')
    simplicity = score_details.get('scoreSimplicity')
    margin_safety = score_details.get('scoreMarginOfSafety')
    composite = score_details.get('compositeScore')
    verdict = score_details.get('verdict')
    confidence = score_details.get('confidence')
    thesis = score_details.get('oneLineThesis')
    risks = score_details.get('keyRisks', [])
    red_flags = score_details.get('redFlags', [])
    exposure = score_details.get('revenueExposure', '{}')
    
    # Construct Prompt
    prompt = f"""Generate a comprehensive Buffett-style buy-side investment memo for {company_name} ({ticker}).
    
INPUT INFORMATION:
- Company: {company_name} ({ticker})
- Sector: {sector}
- Business Description: {description}
- Overall Verdict: {verdict} (Confidence: {confidence})
- Score Breakdown (out of 10):
  * Economic Moat: {moat}
  * Financial Health: {fin_health}
  * Management: {management}
  * Simplicity: {simplicity}
  * Margin of Safety: {margin_safety}
  * Weighted Composite Score: {composite}
- One-line Thesis: {thesis}
- Revenue Exposure segments: {exposure}
- Key Risks: {', '.join(risks) if risks else 'None'}
- Red Flags: {', '.join(red_flags) if red_flags else 'None'}

Please write a highly detailed, professional-grade value-investing research memo. Structure your response EXACTLY as follows (in Markdown format, without any introductory comments):

# Buffett-Style Investment Memo: {company_name} ({ticker})

## 1. Executive Summary & Investment Thesis
Provide a structured synthesis of the recommendation. Detail why this company does or does not fit a Buffett-style portfolio based on the composite score of {composite}/10. Discuss the core one-line thesis: "{thesis}".

## 2. Economic Moat & Competitive Advantages
A qualitative analysis of the company's competitive positioning. Assess the durability of its moat (scored at {moat}/10) using Buffett's criteria: switching costs, network effects, cost advantages, or intangible assets. Address its estimated revenue exposure: {exposure}.

## 3. Financial Health & Business Simplicity
Review the business model's transparency (Simplicity: {simplicity}/10) and financial structure (Financial Health: {fin_health}/10). Evaluate operational risks, return profile consistency, and balance sheet strength.

## 4. Management, Capital Allocation & Governance
Analyze the management team (graded at {management}/10) based on capital allocation choices (ROIC, debt management, share buybacks, and dividend policy). Explicitly address any flagged red flags: {', '.join(red_flags) if red_flags else 'None'}.

## 5. Valuation, Margin of Safety & Major Risks
Evaluate whether the stock offers a sufficient margin of safety (graded at {margin_safety}/10). Outline the critical risks to the long-term compounder thesis (graded key risks: {', '.join(risks) if risks else 'None'}).

*Note: This memo was generated on-demand by the Buffett-Screener Automated Analytics pipeline.*"""

    try:
        memo_content = _call_anthropic_api(api_key, prompt)
    except Exception as e:
        return {
            'statusCode': 502,
            'body': json.dumps({'error': f'Failed to call Anthropic API: {str(e)}'})
        }
        
    # 4. Save to S3
    s3_path = f"dashboard/memos/{run_id}/{ticker}.md"
    if s3_bucket:
        try:
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_path,
                Body=memo_content,
                ContentType='text/markdown'
            )
            print(f"Successfully saved memo to S3: {s3_path}")
        except Exception as e:
            print(f"Error saving memo to S3: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': f'Failed to save memo to S3: {str(e)}'})
            }
            
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': 'SUCCESS',
            'memoPath': s3_path
        })
    }
