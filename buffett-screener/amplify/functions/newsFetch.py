import json
import urllib.request
import urllib.parse
import os
import boto3
import time
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
import re

# Global cache for secret
_NEWS_API_KEY = None

def get_newsapi_key():
    global _NEWS_API_KEY
    if _NEWS_API_KEY:
        return _NEWS_API_KEY
    client = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId='/buffett-screener/news-api-key')
        secret_dict = json.loads(response['SecretString'])
        _NEWS_API_KEY = secret_dict.get('key')
        return _NEWS_API_KEY
    except Exception as e:
        print(f"Error fetching NewsAPI secret: {e}")
        return None

def _fetch_xml_rss(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = []
            for item in root.findall('.//item'):
                title = item.find('title').text if item.find('title') is not None else ''
                desc = item.find('description').text if item.find('description') is not None else ''
                pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
                
                # Basic pubDate parsing or fallback to today
                # A robust app might parse standard RFC 2822 dates here
                
                # Strip HTML from desc
                desc = re.sub(r'<[^>]+>', '', desc).strip()
                
                items.append({
                    'title': title,
                    'summary': desc,
                    'published': pub_date,
                    'source': 'RSS'
                })
            return items
    except Exception as e:
        print(f"RSS fetch failed for {url}: {e}")
        return []

def fetch_rss(ticker, company_name):
    articles = []
    
    # Yahoo
    y_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    articles.extend(_fetch_xml_rss(y_url))
    
    # Google News
    safe_query = urllib.parse.quote(f"{company_name} stock")
    g_url = f"https://news.google.com/rss/search?q={safe_query}&hl=en-US&gl=US&ceid=US:en"
    articles.extend(_fetch_xml_rss(g_url))
    
    return articles

def fetch_newsapi(ticker, company_name, api_key):
    if not api_key:
        return []
    
    query = urllib.parse.quote(f"{company_name} OR {ticker} stock earnings")
    url = f"https://newsapi.org/v2/everything?q={query}&pageSize=5&sortBy=publishedAt&apiKey={api_key}"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            articles = []
            for a in data.get('articles', []):
                articles.append({
                    'title': a.get('title', ''),
                    'summary': a.get('description', ''),
                    'published': a.get('publishedAt', ''),
                    'source': a.get('source', {}).get('name', 'NewsAPI')
                })
            return articles
    except Exception as e:
        print(f"NewsAPI fetch failed for {ticker}: {e}")
        return []

def build_summary(ticker, articles):
    if not articles:
        return f"No recent news found for {ticker}."
        
    # Deduplicate by title similarity
    seen_titles = []
    deduped = []
    for a in articles:
        title = a['title'][:50].lower() # simple prefix matching for deduplication
        is_dup = any(title in seen or seen in title for seen in seen_titles)
        if not is_dup:
            seen_titles.append(title)
            deduped.append(a)
            
    header = f"RECENT NEWS ({ticker}, last 30 days):\n"
    lines = []
    
    for i, a in enumerate(deduped[:8]):
        # Truncate summary to 100 chars
        summary = a['summary'] or ""
        if len(summary) > 100:
            summary = summary[:97] + "..."
            
        date_str = a['published'][:10] if a['published'] else "UNKNOWN"
        lines.append(f"{i+1}. [{date_str}] {a['title']} - {summary}")
        
    full_text = header + "\n".join(lines)
    
    # Hard limit: 800 chars
    if len(full_text) > 800:
        full_text = full_text[:797] + "..."
        
    return full_text

def handler(event, context):
    print("newsFetch started")
    
    candidates = event.get('candidates', [])
    run_id = event.get('run_id', 'UNKNOWN')
    
    api_key = get_newsapi_key()
    news_dict = {}
    
    for c in candidates:
        ticker = c.get('ticker')
        company_name = c.get('name') or c.get('company_name') or ticker
        
        print(f"Fetching news for {ticker}...")
        
        rss_articles = fetch_rss(ticker, company_name)
        newsapi_articles = fetch_newsapi(ticker, company_name, api_key)
        
        combined = rss_articles + newsapi_articles
        
        summary = build_summary(ticker, combined)
        news_dict[ticker] = summary
        
        time.sleep(2) # Rate limit
        
    return {
        'news': news_dict
    }
