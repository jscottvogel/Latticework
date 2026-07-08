import json
import urllib.request
import os
import boto3
import time
import re
from datetime import datetime, timezone, timedelta

# Global cache for secret
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



def get_sp500_tickers(s3_client, bucket_name):
    cache_key = 'tickers-cache/sp500_v2.json'
    cached_tickers = None
    try:
        # Check S3 cache
        obj = s3_client.get_object(Bucket=bucket_name, Key=cache_key)
        last_modified = obj['LastModified']
        data = json.loads(obj['Body'].read().decode('utf-8'))
        cached_tickers = data.get('tickers', [])
        if datetime.now(timezone.utc) - last_modified < timedelta(days=7):
            return cached_tickers
    except s3_client.exceptions.NoSuchKey:
        pass
    except Exception as e:
        print(f"S3 cache check failed: {e}")

    # Fetch from Wikipedia
    print("Fetching S&P 500 from Wikipedia...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            # Extract the first table (S&P 500 component stocks)
            table_match = re.search(r'<table[^>]*id="constituents"[^>]*>(.*?)</table>', html, re.DOTALL)
            if not table_match:
                raise ValueError("Could not find table in HTML")
            
            # Extract tickers from the first column of each row
            # Usually <a ...>TICKER</a> or just TICKER
            tickers = []
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_match.group(1), re.DOTALL)
            for row in rows[1:]: # Skip header
                cols = re.findall(r'<td.*?>(.*?)</td>', row, re.DOTALL)
                if cols:
                    # Strip tags and clean up ticker (e.g. BRK.B -> BRK-B)
                    ticker_raw = re.sub(r'<.*?>', '', cols[0]).strip()
                    ticker = ticker_raw.replace('.', '-')
                    if ticker:
                        tickers.append(ticker)
            
            if not tickers:
                raise ValueError("Parsed 0 tickers from Wikipedia constituents table.")
            
            # Save to S3
            if tickers and bucket_name:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=cache_key,
                    Body=json.dumps({"tickers": tickers})
                )
            return tickers
    except Exception as e:
        print(f"Failed to fetch from Wikipedia: {e}")
        if cached_tickers:
            print("Falling back to expired S3 cached tickers.")
            return cached_tickers
        return []

def get_ticker_group(all_tickers, run_id):
    # run_id format: YYYY-DNNN, extract NNN
    try:
        day_num = int(run_id.split('-D')[-1])
    except:
        day_num = 1
    
    # Partition into 7 groups to ensure all stocks are evaluated at least once a week (7 days)
    group_idx = day_num % 7
    group_size = len(all_tickers) // 7
    start = group_idx * group_size
    # If it's the last group, take all remaining
    end = start + group_size if group_idx < 6 else len(all_tickers)
    return all_tickers[start:end]

def _fetch_av(endpoint, ticker, api_key):
    url = f"https://www.alphavantage.co/query?function={endpoint}&symbol={ticker}&entitlement=delayed&apikey={api_key}"
    max_retries = 5
    retry_delay = 60  # Sleep 60 seconds if rate limit is hit to completely reset the minute window
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            start_t = time.time()
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                ms = int((time.time() - start_t) * 1000)
                
                # Check for Alpha Vantage rate limiting warnings
                if "Note" in data:
                    note = data.get('Note', '')
                    if api_key:
                        note = note.replace(api_key, '********')
                    print(f"Rate limit hit (Note) on attempt {attempt+1} for {endpoint} {ticker}. Sleeping {retry_delay}s: {note}")
                    time.sleep(retry_delay)
                    continue
                if "Information" in data:
                    info = data.get('Information', '')
                    if api_key:
                        info = info.replace(api_key, '********')
                    print(f"Rate limit hit (Information) on attempt {attempt+1} for {endpoint} {ticker}. Sleeping {retry_delay}s: {info}")
                    time.sleep(retry_delay)
                    continue
                
                print(f"API {endpoint} {ticker} - {ms}ms - 200")
                return data
        except Exception as e:
            err_msg = str(e)
            if api_key:
                err_msg = err_msg.replace(api_key, '********')
            print(f"API {endpoint} {ticker} failed on attempt {attempt+1}: {err_msg}")
            time.sleep(5)
            
    return {}

def _safe_float(val):
    try:
        return float(val)
    except:
        return None

def fetch_overview(ticker, api_key):
    data = _fetch_av('OVERVIEW', ticker, api_key)
    return {
        'name': data.get('Name'),
        'sector': data.get('Sector'),
        'roe': _safe_float(data.get('ReturnOnEquityTTM')),
        'net_margin': _safe_float(data.get('ProfitMargin')),
        'debt_to_equity': _safe_float(data.get('DebtToEquityRatio')),
        'pe_ratio': _safe_float(data.get('PERatio')),
        'eps': _safe_float(data.get('EPS')),
        'high_52w': _safe_float(data.get('52WeekHigh')),
        'low_52w': _safe_float(data.get('52WeekLow')),
        'shares_out': _safe_float(data.get('SharesOutstanding'))
    }

def fetch_cash_flow(ticker, api_key):
    data = _fetch_av('CASH_FLOW', ticker, api_key)
    reports = data.get('annualReports', [])
    fcf_values = []
    for rep in reports[:4]:
        ocf = _safe_float(rep.get('operatingCashflow'))
        capex = _safe_float(rep.get('capitalExpenditures'))
        if ocf is not None and capex is not None:
            fcf_values.append(ocf - capex) # Note: capex might be negative or positive depending on accounting standard, assuming positive deduction here
            # Actually, AV returns negative for capex often. Let's do absolute value deduction.
            # safe assumption: fcf = ocf - abs(capex) if capex != 0
    
    # Actually, standard is OCF - CapEx (if CapEx is positive), or OCF + CapEx (if CapEx is negative).
    # Let's just do OCF - abs(capex).
    fcf_cleaned = []
    for rep in reports[:4]:
        ocf = _safe_float(rep.get('operatingCashflow'))
        capex = _safe_float(rep.get('capitalExpenditures'))
        if ocf is not None and capex is not None:
            fcf_cleaned.append(ocf - abs(capex))
            
    def _safe_cagr(start, end, periods):
        if start is None or end is None or periods <= 0:
            return None
        if start <= 0 or end <= 0:
            # Simplistic handling: if start or end is negative/zero, standard CAGR formula breaks.
            return None
        return (end / start) ** (1/periods) - 1
            
    fcf_growth_3yr = None
    if len(fcf_cleaned) >= 4:
        fcf_growth_3yr = _safe_cagr(fcf_cleaned[3], fcf_cleaned[0], 3)
            
    return {
        'fcf_growth_3yr': fcf_growth_3yr,
        'fcf_values': fcf_cleaned
    }

def fetch_income(ticker, api_key):
    data = _fetch_av('INCOME_STATEMENT', ticker, api_key)
    reports = data.get('annualReports', [])
    eps_growth_5yr = None
    net_margin_calc = None
    
    if len(reports) >= 6:
        current_ni = _safe_float(reports[0].get('netIncome'))
        past_ni = _safe_float(reports[5].get('netIncome'))
        if past_ni and past_ni > 0 and current_ni and current_ni > 0:
            eps_growth_5yr = (current_ni / past_ni) ** (1/5) - 1
            
    if len(reports) >= 1:
        ni = _safe_float(reports[0].get('netIncome'))
        rev = _safe_float(reports[0].get('totalRevenue'))
        if ni is not None and rev and rev > 0:
            net_margin_calc = ni / rev
            
    return {
        'eps_growth_5yr': eps_growth_5yr,
        'net_margin_calc': net_margin_calc
    }

def fetch_balance(ticker, api_key):
    data = _fetch_av('BALANCE_SHEET', ticker, api_key)
    reports = data.get('annualReports', [])
    current_ratio = None
    debt_equity = None
    if len(reports) > 0:
        rep = reports[0]
        tca = _safe_float(rep.get('totalCurrentAssets'))
        tcl = _safe_float(rep.get('totalCurrentLiabilities'))
        if tca and tcl and tcl > 0:
            current_ratio = tca / tcl
            
        tl = _safe_float(rep.get('totalLiabilities'))
        tse = _safe_float(rep.get('totalShareholderEquity'))
        if tl and tse and tse > 0:
            debt_equity = tl / tse
            
    return {
        'current_ratio_calc': current_ratio,
        'debt_equity_calc': debt_equity
    }

def fetch_all_metrics(ticker, api_key, av_tier='premium'):
    spacing = 15.0 if av_tier == 'free' else 0.9
    ov = fetch_overview(ticker, api_key)
    time.sleep(spacing) # Sleep between requests for the same ticker to avoid sub-second rate limits
    cf = fetch_cash_flow(ticker, api_key)
    time.sleep(spacing)
    inc = fetch_income(ticker, api_key)
    time.sleep(spacing)
    bal = fetch_balance(ticker, api_key)
    
    # Merge logic
    # earnings yield = 1 / pe
    ey = None
    pe = ov.get('pe_ratio')
    if pe and pe > 0:
        ey = 1 / pe
        
    pct_from_high = None
    current_price = None # AV OVERVIEW doesn't give real-time price. We'd need GLOBAL_QUOTE. But we can approximate or skip if missing.
    # We will just skip real-time price for now to save API calls.
    
    return {
        'ticker': ticker,
        'name': ov.get('name'),
        'sector': ov.get('sector'),
        'roe5yrAvg': ov.get('roe'), # using TTM ROE as proxy
        'netMargin': inc.get('net_margin_calc') or ov.get('net_margin'),
        'debtToEquity': bal.get('debt_equity_calc') or ov.get('debt_to_equity'),
        'fcfGrowth3yr': cf.get('fcf_growth_3yr'),
        'epsGrowth5yr': inc.get('eps_growth_5yr'),
        'currentRatio': bal.get('current_ratio_calc'),
        'peRatio': pe,
        'earningsYield': ey,
        'pctFrom52wHigh': None,
        'fetchedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }

def handler(event, context):
    print("dataFetch started")
    
    run_id = event.get('run_id', datetime.now(timezone.utc).strftime("%Y-W%V"))
    s3_bucket = os.environ.get('S3_BUCKET')
    db_table = os.environ.get('DYNAMODB_TABLE_RAW_FINANCIALS')
    av_tier = os.environ.get('ALPHA_VANTAGE_TIER', 'premium') # Default to premium as requested
    
    s3 = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    
    api_key = get_secret('/buffett-screener/alpha-vantage-key')
    
    # Load queue state from S3
    queue_key = 'tickers-cache/fetch-queue_v1.json'
    queue_state = {}
    if s3_bucket:
        try:
            obj = s3.get_object(Bucket=s3_bucket, Key=queue_key)
            queue_state = json.loads(obj['Body'].read().decode('utf-8'))
        except s3.exceptions.NoSuchKey:
            print("Fetch queue not found in S3, will initialize a new one.")
        except Exception as e:
            print(f"Failed to read fetch queue from S3: {e}")
            
    tickers = event.get('tickers')
    if not tickers:
        all_tickers = get_sp500_tickers(s3, s3_bucket)
        if not all_tickers:
            raise ValueError("Failed to fetch S&P 500 tickers. Aborting run.")
            
        # Check for limit on S&P 500 stocks (defaults to 0, which means no limit/evaluate all ~500 stocks)
        limit_sp500 = int(os.environ.get('LIMIT_SP500_TICKERS', '0'))
        if limit_sp500 > 0:
            print(f"Limiting S&P 500 tickers list from {len(all_tickers)} to the first {limit_sp500} tickers.")
            all_tickers = all_tickers[:limit_sp500]
            
        # Initialize queue state for any tickers that aren't in it
        for t in all_tickers:
            if t not in queue_state:
                queue_state[t] = {"lastFetched": None, "lastStatus": "PENDING"}
        
        # Clean up queue state: remove any tickers no longer in all_tickers
        all_tickers_set = set(all_tickers)
        queue_state = {t: v for t, v in queue_state.items() if t in all_tickers_set}
        
        previous_top_tickers = event.get('previous_top_tickers', [])
        
        # Define target count. Default to 1/7th of S&P 500 (approx 71 stocks)
        target_count = len(all_tickers) // 7
        if target_count < 10:
            target_count = 10
        if len(all_tickers) <= target_count:
            target_count = len(all_tickers)
            
        tickers = []
        seen = set()
        
        # 1. Add previous top tickers first (leaderboard priority)
        for pt in previous_top_tickers:
            if pt in queue_state and pt not in seen:
                tickers.append(pt)
                seen.add(pt)
                
        # 2. Add failed tickers next (retry priority)
        def get_last_fetched_sort_key(t):
            lf = queue_state[t].get('lastFetched')
            return (lf is not None, lf or "")
            
        failed_tickers = [t for t, state in queue_state.items() if state.get('lastStatus') == 'FAILED']
        failed_tickers.sort(key=get_last_fetched_sort_key)
        for ft in failed_tickers:
            if ft not in seen and len(tickers) < target_count:
                tickers.append(ft)
                seen.add(ft)
                
        # 3. Fill the remaining quota with the oldest fetched tickers (lastFetched is None/oldest first)
        remaining_candidates = [t for t in all_tickers if t not in seen]
        remaining_candidates.sort(key=get_last_fetched_sort_key)
        for rt in remaining_candidates:
            if len(tickers) < target_count:
                tickers.append(rt)
                seen.add(rt)
        
    print(f"Fetching data for {len(tickers)} tickers in run {run_id}...")
    
    all_metrics = []
    
    table = dynamodb.Table(db_table) if db_table else None
    
    sleep_time = 0.9 if av_tier == 'premium' else 12.0

    for i, ticker in enumerate(tickers):
        print(f"Processing {ticker} ({i+1}/{len(tickers)})...")
        metrics = fetch_all_metrics(ticker, api_key, av_tier)
        all_metrics.append(metrics)
        
        # Check if the fetch succeeded
        fetch_success = metrics.get('name') is not None
        
        # Update queue state
        if s3_bucket and ticker in queue_state:
            if fetch_success:
                queue_state[ticker] = {
                    "lastFetched": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    "lastStatus": "SUCCESS"
                }
            else:
                queue_state[ticker] = {
                    "lastFetched": queue_state[ticker].get('lastFetched'),
                    "lastStatus": "FAILED"
                }
        
        if table:
            # DynamoDB requires floats to be cast to Decimal. For simplicity in batch_writer, 
            # we convert floats to strings or Decimal. JSON float to string is easiest.
            item = {k: str(v) if isinstance(v, float) else v for k, v in metrics.items() if v is not None}
            item['ticker'] = ticker
            item['runId'] = run_id
            try:
                table.put_item(Item=item)
            except Exception as e:
                print(f"DynamoDB write failed for {ticker}: {e}")
        
        time.sleep(sleep_time)
        
    # Save complete JSON to S3
    s3_key = f'raw-financials/{run_id}/all_metrics.json'
    if s3_bucket:
        s3.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=json.dumps(all_metrics)
        )
        
        # Save updated queue state to S3
        if queue_state:
            try:
                s3.put_object(
                    Bucket=s3_bucket,
                    Key=queue_key,
                    Body=json.dumps(queue_state)
                )
                print("Successfully saved updated fetch queue to S3.")
            except Exception as e:
                print(f"Failed to save fetch queue to S3: {e}")
        
    return {
        's3_key': s3_key,
        'metrics': all_metrics
    }
