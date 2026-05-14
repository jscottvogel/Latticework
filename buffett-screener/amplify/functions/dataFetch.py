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
        secret_dict = json.loads(response['SecretString'])
        _ALPHA_VANTAGE_KEY = secret_dict.get('key')
        return _ALPHA_VANTAGE_KEY
    except Exception as e:
        print(f"Error fetching secret: {e}")
        return None

def get_sp500_tickers(s3_client, bucket_name):
    cache_key = 'tickers-cache/sp500_v2.json'
    try:
        # Check S3 cache
        obj = s3_client.get_object(Bucket=bucket_name, Key=cache_key)
        last_modified = obj['LastModified']
        if datetime.now(timezone.utc) - last_modified < timedelta(days=7):
            data = json.loads(obj['Body'].read().decode('utf-8'))
            return data.get('tickers', [])
    except s3_client.exceptions.NoSuchKey:
        pass
    except Exception as e:
        print(f"S3 cache check failed: {e}")

    # Fetch from Wikipedia
    print("Fetching S&P 500 from Wikipedia...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
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
            rows = re.findall(r'<tr>(.*?)</tr>', table_match.group(1), re.DOTALL)
            for row in rows[1:]: # Skip header
                cols = re.findall(r'<td.*?>(.*?)</td>', row, re.DOTALL)
                if cols:
                    # Strip tags and clean up ticker (e.g. BRK.B -> BRK-B)
                    ticker_raw = re.sub(r'<.*?>', '', cols[0]).strip()
                    ticker = ticker_raw.replace('.', '-')
                    if ticker:
                        tickers.append(ticker)
            
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
        return []

def get_ticker_group(all_tickers, run_id):
    # run_id format: YYYY-WNN, extract NN
    try:
        week_num = int(run_id.split('-W')[-1])
    except:
        week_num = 1
    
    group_idx = week_num % 10
    group_size = len(all_tickers) // 10
    start = group_idx * group_size
    # If it's the last group, take all remaining
    end = start + group_size if group_idx < 9 else len(all_tickers)
    return all_tickers[start:end]

def _fetch_av(endpoint, ticker, api_key):
    url = f"https://www.alphavantage.co/query?function={endpoint}&symbol={ticker}&apikey={api_key}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        start_t = time.time()
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            ms = int((time.time() - start_t) * 1000)
            print(f"API {endpoint} {ticker} - {ms}ms - 200")
            return data
    except Exception as e:
        print(f"API {endpoint} {ticker} failed: {e}")
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
            
    fcf_growth_3yr = None
    if len(fcf_cleaned) >= 4:
        current = fcf_cleaned[0]
        past = fcf_cleaned[3]
        if past and past > 0:
            fcf_growth_3yr = (current / past) ** (1/3) - 1
            
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
        if past_ni and past_ni > 0 and current_ni:
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

def fetch_all_metrics(ticker, api_key):
    ov = fetch_overview(ticker, api_key)
    cf = fetch_cash_flow(ticker, api_key)
    inc = fetch_income(ticker, api_key)
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
        'fetchedAt': datetime.now(timezone.utc).isoformat()
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
    
    all_tickers = get_sp500_tickers(s3, s3_bucket)
    if not all_tickers:
        all_tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN'] # Fallback
        
    # If event explicitly provided tickers, use those (e.g. for testing)
    tickers = event.get('tickers')
    if not tickers:
        tickers = get_ticker_group(all_tickers, run_id)
        
    print(f"Fetching data for {len(tickers)} tickers in run {run_id}...")
    
    all_metrics = []
    
    table = dynamodb.Table(db_table) if db_table else None
    
    sleep_time = 1.0 if av_tier == 'premium' else 12.0

    for i, ticker in enumerate(tickers):
        print(f"Processing {ticker} ({i+1}/{len(tickers)})...")
        metrics = fetch_all_metrics(ticker, api_key)
        all_metrics.append(metrics)
        
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
        
    return {
        's3_key': s3_key,
        'metrics': all_metrics
    }
