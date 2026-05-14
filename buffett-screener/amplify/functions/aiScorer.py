import json
import urllib.request
import urllib.error
import os
import boto3
import time

_ANTHROPIC_KEY = None

def get_anthropic_key():
    global _ANTHROPIC_KEY
    if _ANTHROPIC_KEY:
        return _ANTHROPIC_KEY
    client = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId='/buffett-screener/anthropic-api-key')
        secret_dict = json.loads(response['SecretString'])
        _ANTHROPIC_KEY = secret_dict.get('key')
        return _ANTHROPIC_KEY
    except Exception as e:
        print(f"Error fetching Anthropic secret: {e}")
        return None

BUFFETT_SYSTEM_PROMPT = """You are a disciplined value investing analyst trained in the philosophy of Warren Buffett and Charlie Munger. Evaluate stocks that have passed an initial quantitative screen. Return ONLY valid JSON, no other text.

PHILOSOPHY:
- Favor businesses with durable competitive advantages (moats)
- Prefer simple, understandable business models
- Distrust complexity, financial engineering, and hype
- Think in decades not quarters
- Skeptical of analyst consensus and media narratives
- Price is what you pay, value is what you get

SCORING RUBRIC (score each 1-10):

1. MOAT (score_moat):
   Pricing power? High switching costs or network effects?
   ROE consistently >15% for 5+ years?
   Difficult for competitors to replicate?

2. FINANCIAL HEALTH (score_financial_health):
   FCF consistently positive and growing?
   Debt manageable (D/E < 0.5 preferred)?
   Margins stable or expanding?
   EPS growth consistent rather than lumpy?

3. MANAGEMENT QUALITY (score_management):
   Buying back shares at sensible prices?
   Capital allocation disciplined?
   Any headlines suggesting integrity issues?
   Meaningful insider ownership?

4. BUSINESS SIMPLICITY (score_simplicity):
   Explainable in one sentence?
   Straightforward revenue model?
   Relatively immune to technological disruption?

5. MARGIN OF SAFETY (score_margin_of_safety):
   P/E reasonable vs. sector averages?
   Earnings yield attractive vs. 10-year Treasury (~4.5%)?
   Meaningfully below 52-week high?
   Price reflects pessimism rather than optimism?

REQUIRED OUTPUT FORMAT — return ONLY this JSON object:
{
  "ticker": "XXXX",
  "company_name": "Full Name",
  "scores": {
    "moat": 7,
    "financial_health": 8,
    "management": 6,
    "simplicity": 9,
    "margin_of_safety": 5
  },
  "composite_score": 7.0,
  "one_line_thesis": "Under 120 characters",
  "key_risks": ["risk1", "risk2"],
  "red_flags": [],
  "verdict": "INVESTIGATE",
  "confidence": "HIGH"
}

composite_score = moat*0.30 + financial_health*0.25 + management*0.20 + simplicity*0.15 + margin_of_safety*0.10

RULES:
- Never recommend buying or selling. Research only.
- Flag accounting irregularities in red_flags.
- If data insufficient: confidence = LOW.
- verdict: INVESTIGATE if composite>=7, MONITOR if 5-7, AVOID if <5.
- Reward consistency. Penalise debt and complexity."""

def build_user_message(metrics, news_summary):
    def fmt_pct(val):
        return f"{val:.1%}" if val is not None else "N/A"
    
    def fmt_flt(val, dec=2):
        return f"{val:.{dec}f}" if val is not None else "N/A"

    return f"""Evaluate for Buffett-style value investing:
COMPANY: {metrics.get('name', 'Unknown')} ({metrics.get('ticker', 'Unknown')})
SECTOR: {metrics.get('sector', 'Unknown')}

FINANCIAL METRICS:
- ROE (5yr avg): {fmt_pct(metrics.get('roe5yrAvg'))}
- Net Margin: {fmt_pct(metrics.get('netMargin'))}
- Debt/Equity: {fmt_flt(metrics.get('debtToEquity'), 2)}
- FCF Growth (3yr): {fmt_pct(metrics.get('fcfGrowth3yr'))}
- EPS Growth (5yr): {fmt_pct(metrics.get('epsGrowth5yr'))}
- Current Ratio: {fmt_flt(metrics.get('currentRatio'), 2)}
- P/E Ratio: {fmt_flt(metrics.get('peRatio'), 1)}
- Earnings Yield: {fmt_pct(metrics.get('earningsYield'))}
- % From 52-Week High: {fmt_pct(metrics.get('pctFrom52wHigh'))}

RECENT NEWS:
{news_summary}"""

def _call_anthropic_api(api_key, user_msg, force_json=False):
    url = "https://api.anthropic.com/v1/messages"
    
    sys_prompt = BUFFETT_SYSTEM_PROMPT
    if force_json:
        sys_prompt += "\n\nCRITICAL: YOU MUST RETURN ONLY VALID JSON. NO PREAMBLE. NO EXPLANATION."
        
    payload = {
        "model": "claude-3-haiku-20240307", # standard latest claude 3 haiku
        "max_tokens": 600,
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
            return res
    except urllib.error.HTTPError as e:
        print(f"Anthropic API Error: {e.read().decode('utf-8')}")
        raise e

def score_stock(metrics, news_summary, api_key):
    user_msg = build_user_message(metrics, news_summary)
    
    def attempt(force_json=False):
        res = _call_anthropic_api(api_key, user_msg, force_json)
        content = res['content'][0]['text']
        input_tokens = res['usage']['input_tokens']
        output_tokens = res['usage']['output_tokens']
        
        # Strip potential markdown block
        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
            
        parsed = json.loads(content)
        parsed['input_tokens'] = input_tokens
        parsed['output_tokens'] = output_tokens
        return parsed

    try:
        return attempt(False)
    except Exception as e:
        print(f"Parse error on first attempt for {metrics.get('ticker')}: {e}. Retrying with force_json...")
        try:
            return attempt(True)
        except Exception as e2:
            print(f"Second attempt failed for {metrics.get('ticker')}: {e2}")
            return {
                "ticker": metrics.get('ticker'),
                "company_name": metrics.get('name'),
                "scores": {},
                "composite_score": 0.0,
                "one_line_thesis": "Error calling AI",
                "key_risks": [],
                "red_flags": ["AI Failure"],
                "verdict": "AVOID",
                "confidence": "LOW",
                "input_tokens": 0,
                "output_tokens": 0
            }

def estimate_cost(input_tokens, output_tokens):
    # Haiku pricing: $0.25 per 1M input, $1.25 per 1M output (latest pricing, adjusting from $0.8/$4)
    # The prompt specified $0.80 and $4.00, I will use that to match exact expectations.
    in_cost = (input_tokens / 1_000_000.0) * 0.80
    out_cost = (output_tokens / 1_000_000.0) * 4.00
    return in_cost + out_cost

def handler(event, context):
    print("aiScorer started")
    
    run_id = event.get('run_id')
    candidates = event.get('candidates', [])
    
    api_key = get_anthropic_key()
    if not api_key:
        print("Anthropic API key not found.")
        return {'scores': [], 'total_cost_usd': 0.0}
        
    total_input_tokens = 0
    total_output_tokens = 0
    scores = []
    
    for i, candidate in enumerate(candidates):
        ticker = candidate.get('ticker')
        metrics = candidate.get('metrics', candidate) # fallback if flat structure
        news_summary = candidate.get('news_summary', 'No recent news.')
        
        result = score_stock(metrics, news_summary, api_key)
        scores.append(result)
        
        in_tok = result.get('input_tokens', 0)
        out_tok = result.get('output_tokens', 0)
        total_input_tokens += in_tok
        total_output_tokens += out_tok
        
        print(f"Scored {ticker} ({i+1}/{len(candidates)}): {result.get('composite_score', 0):.1f} [{result.get('verdict')}]")
        
        time.sleep(1) # API rate limits
        
    # Sort and assign ranks
    scores.sort(key=lambda x: x.get('composite_score', 0), reverse=True)
    for idx, s in enumerate(scores):
        s['rank_this_week'] = idx + 1
        
    total_cost = estimate_cost(total_input_tokens, total_output_tokens)
    print(f"Total tokens: {total_input_tokens} in / {total_output_tokens} out. Est Cost: ${total_cost:.4f}")
    
    # Save to DynamoDB
    db_table = os.environ.get('DYNAMODB_TABLE_STOCK_SCORES')
    if db_table and scores:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(db_table)
        
        import decimal
        with table.batch_writer() as batch:
            for s in scores:
                
                def to_dec(val):
                    if val is None: return None
                    try:
                        return decimal.Decimal(str(val))
                    except:
                        return None
                        
                item = {
                    'runId': run_id,
                    'ticker': s['ticker'],
                    'companyName': s.get('company_name'),
                    'scoreMoat': to_dec(s.get('scores', {}).get('moat')),
                    'scoreFinancialHealth': to_dec(s.get('scores', {}).get('financial_health')),
                    'scoreManagement': to_dec(s.get('scores', {}).get('management')),
                    'scoreSimplicity': to_dec(s.get('scores', {}).get('simplicity')),
                    'scoreMarginOfSafety': to_dec(s.get('scores', {}).get('margin_of_safety')),
                    'compositeScore': to_dec(s.get('composite_score')),
                    'verdict': s.get('verdict'),
                    'confidence': s.get('confidence'),
                    'oneLineThesis': s.get('one_line_thesis'),
                    'keyRisks': s.get('key_risks', []),
                    'redFlags': s.get('red_flags', []),
                    'rankThisWeek': s.get('rank_this_week'),
                    'createdAt': datetime.now(timezone.utc).isoformat(),
                    '__typename': 'StockScore'
                }
                # Clean up empty lists
                if not item['keyRisks']: item['keyRisks'] = ['None']
                if not item['redFlags']: item['redFlags'] = ['None']
                
                # Keep them as lists so boto3 saves them as 'L' matching a.string().array()
                item['keyRisks'] = list(item['keyRisks'])
                item['redFlags'] = list(item['redFlags'])
                
                batch.put_item(Item=item)

    return {
        'scores': scores,
        'total_input_tokens': total_input_tokens,
        'total_output_tokens': total_output_tokens,
        'total_cost_usd': total_cost
    }
