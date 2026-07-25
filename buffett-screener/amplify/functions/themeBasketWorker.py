import json
import os
import boto3
import decimal
from datetime import datetime, timezone
import re

# Helper class to convert DynamoDB decimals to JSON numbers
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 == 0:
                return int(o)
            return float(o)
        return super(DecimalEncoder, self).default(o)

def handler(event, context):
    print("themeBasketWorker started")
    
    s3_bucket = os.environ.get('S3_BUCKET')
    registry_table_name = os.environ.get('DYNAMODB_TABLE_THEME_REGISTRY')
    basket_table_name = os.environ.get('DYNAMODB_TABLE_THEME_BASKET')
    rolling_table_name = os.environ.get('DYNAMODB_TABLE_ROLLING_SCORES')
    
    s3 = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    
    # 1. Fetch tables
    registry_table = dynamodb.Table(registry_table_name)
    basket_table = dynamodb.Table(basket_table_name)
    rolling_table = dynamodb.Table(rolling_table_name)
    
    # 2. Seed Default Themes if empty
    themes = []
    try:
        response = registry_table.scan()
        themes = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = registry_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            themes.extend(response.get('Items', []))
        
        default_themes = [
            {
                'themeId': 'saas-cloud',
                'name': 'SaaS & Cloud Infrastructure',
                'description': 'Companies building subscription software, cloud platforms, and digital enterprise infrastructure.',
                'keywords': ['saas', 'cloud', 'software', 'subscription', 'enterprise software', 'infrastructure']
            },
            {
                'themeId': 'ai-semiconductors',
                'name': 'Artificial Intelligence & Semiconductors',
                'description': 'Hardware, chip designs, GPUs, and software systems powering artificial intelligence and next-generation compute.',
                'keywords': ['ai', 'artificial intelligence', 'semiconductor', 'chip', 'gpu', 'nvidia', 'processor']
            },
            {
                'themeId': 'healthcare-biotech',
                'name': 'Healthcare & Biotechnology',
                'description': 'Medical device innovations, biotechnology research, therapeutics, and healthcare providers.',
                'keywords': ['healthcare', 'medical', 'biotech', 'biotechnology', 'pharma', 'therapeutics', 'clinical']
            },
            {
                'themeId': 'clean-energy',
                'name': 'Clean Energy & EV Technology',
                'description': 'Renewable energy generation, electric vehicles, battery hardware, solar power, and carbon reductions.',
                'keywords': ['electric vehicle', 'ev', 'solar', 'wind', 'clean energy', 'battery', 'renewable']
            },
            {
                'themeId': 'consumer-moats',
                'name': 'Consumer Moats & Brand Franchises',
                'description': 'Classic Buffett-style franchises with strong brand equity, customer loyalty, and high pricing power.',
                'keywords': ['consumer', 'brand', 'franchise', 'retail', 'coca-cola', 'beverage', 'food', 'pricing power', 'apple', 'apparel']
            },
            {
                'themeId': 'financials-insurance',
                'name': 'Financials & Insurance Networks',
                'description': 'Steady underwriting businesses, banking institutions, and card networks generating low-cost capital float.',
                'keywords': ['financial', 'insurance', 'bank', 'credit', 'banking', 'underwriting', 'reinsurance', 'payments', 'brokerage']
            },
            {
                'themeId': 'industrial-infra',
                'name': 'Industrial Infrastructure & Logistics',
                'description': 'Asset-heavy networks with high capital barriers to entry, including railways, utilities, and energy distribution.',
                'keywords': ['industrial', 'energy', 'railroad', 'utility', 'transportation', 'logistics', 'machinery', 'infrastructure', 'pipeline']
            }
        ]
        
        # Check for missing default themes and seed them
        themes_map = {t['themeId']: t for t in themes}
        seeded_new = False
        with registry_table.batch_writer() as batch:
            for dt in default_themes:
                if dt['themeId'] not in themes_map:
                    print(f"Seeding missing theme: {dt['themeId']}")
                    dt['__typename'] = 'ThemeRegistry'
                    dt['createdAt'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                    dt['updatedAt'] = dt['createdAt']
                    batch.put_item(Item=dt)
                    themes.append(dt)
                    seeded_new = True
        if seeded_new:
            print("Successfully seeded missing default themes.")
    except Exception as e:
        print(f"Error checking/seeding Theme Registry: {e}")
        return {'status': 'FAILED', 'reason': f"REGISTRY_READ_ERROR: {str(e)}"}

    # 3. Scan Rolling Scores
    rolling_scores = []
    try:
        response = rolling_table.scan()
        rolling_scores = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = rolling_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            rolling_scores.extend(response.get('Items', []))
    except Exception as e:
        print(f"Error scanning Rolling Scores: {e}")
        return {'status': 'FAILED', 'reason': f"ROLLING_SCAN_ERROR: {str(e)}"}
        
    print(f"Total rolling scores found: {len(rolling_scores)}")

    # 4. Clear current Theme Basket table
    try:
        response = basket_table.scan(ProjectionExpression="themeId, ticker")
        existing_baskets = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = basket_table.scan(ProjectionExpression="themeId, ticker", ExclusiveStartKey=response['LastEvaluatedKey'])
            existing_baskets.extend(response.get('Items', []))
            
        if existing_baskets:
            # Deduplicate by key to prevent ValidationException in batch_writer
            unique_keys = {}
            for item in existing_baskets:
                key = (item['themeId'], item['ticker'])
                unique_keys[key] = item
            print(f"Clearing {len(unique_keys)} unique theme basket entries (from {len(existing_baskets)} scanned entries)...")
            with basket_table.batch_writer() as batch:
                for item in unique_keys.values():
                    batch.delete_item(Key={'themeId': item['themeId'], 'ticker': item['ticker']})
    except Exception as e:
        print(f"Warning: Error clearing ThemeBasket table: {e}")

    # 5. Evaluate matching criteria
    basket_entries = []
    theme_baskets_summary = {}
    
    # Initialize summary map
    for theme in themes:
        theme_baskets_summary[theme['themeId']] = {
            'themeId': theme['themeId'],
            'name': theme['name'],
            'description': theme.get('description', ''),
            'stocks': []
        }

    for score in rolling_scores:
        ticker = score['ticker']
        company_name = score.get('companyName') or ''
        sector = score.get('sector') or ''
        latest_thesis = score.get('latestThesis') or ''
        latest_verdict = score.get('latestVerdict') or ''
        
        # Combine fields into a search string for keyword scanning
        search_blob = " ".join([
            ticker.lower(),
            company_name.lower(),
            sector.lower(),
            latest_thesis.lower(),
            latest_verdict.lower()
        ])
        
        for theme in themes:
            theme_id = theme['themeId']
            keywords = theme.get('keywords', [])
            
            matched_keywords = []
            for kw in keywords:
                if kw.startswith('r/') and kw.endswith('/'):
                    pattern = kw[2:-1]
                    try:
                        if re.search(pattern, search_blob, re.IGNORECASE):
                            matched_keywords.append(kw)
                    except Exception as re_err:
                        print(f"Error compiling custom regex pattern '{pattern}': {re_err}")
                else:
                    # Use regex word boundaries for precise matching
                    pattern = r'\b' + re.escape(kw.lower()) + r'\b'
                    if re.search(pattern, search_blob):
                        matched_keywords.append(kw)
                    
            if matched_keywords:
                # We have a match!
                avg_score = score.get('avgCompositeScore', decimal.Decimal('0.0'))
                is_investable = score.get('isInvestable', False)
                
                basket_item = {
                    'themeId': theme_id,
                    'ticker': ticker,
                    'companyName': company_name,
                    'sector': sector,
                    'avgCompositeScore': avg_score,
                    'latestVerdict': latest_verdict,
                    'isInvestable': is_investable,
                    'matchedKeywords': matched_keywords,
                    '__typename': 'ThemeBasket',
                    'createdAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    'updatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                }
                
                basket_entries.append(basket_item)
                
                # Add to summary object for S3 export
                theme_baskets_summary[theme_id]['stocks'].append({
                    'ticker': ticker,
                    'companyName': company_name,
                    'sector': sector,
                    'avgCompositeScore': float(avg_score) if isinstance(avg_score, decimal.Decimal) else avg_score,
                    'latestVerdict': latest_verdict,
                    'isInvestable': is_investable,
                    'matchedKeywords': matched_keywords
                })

    # Write matches to ThemeBasket table
    if basket_entries:
        # Deduplicate entries by themeId and ticker
        unique_entries = {}
        for entry in basket_entries:
            key = (entry['themeId'], entry['ticker'])
            unique_entries[key] = entry
        print(f"Writing {len(unique_entries)} unique matched theme basket entries (from {len(basket_entries)} entries)...")
        try:
            with basket_table.batch_writer() as batch:
                for entry in unique_entries.values():
                    batch.put_item(Item=entry)
        except Exception as e:
            print(f"Error writing to ThemeBasket: {e}")
            return {'status': 'FAILED', 'reason': f"BASKET_WRITE_ERROR: {str(e)}"}
            
    # 6. Export theme baskets JSON to S3
    if s3_bucket:
        try:
            summary_data = {
                'updatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'baskets': theme_baskets_summary
            }
            s3.put_object(
                Bucket=s3_bucket,
                Key='dashboard/theme_baskets.json',
                Body=json.dumps(summary_data, cls=DecimalEncoder, default=str),
                ContentType='application/json'
            )
            print("Successfully exported theme_baskets.json to S3.")
        except Exception as e:
            print(f"Error exporting theme baskets to S3: {e}")
            
    return {
        'status': 'SUCCESS',
        'themesMatched': len(themes),
        'totalMatches': len(basket_entries)
    }
