import os
import json
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3
import decimal

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../amplify/functions')))

import themeBasketWorker

@pytest.fixture
def setup_aws(env_setup):
    with mock_aws():
        # Set environment variables for testing
        os.environ['DYNAMODB_TABLE_THEME_REGISTRY'] = 'TestThemeRegistry'
        os.environ['DYNAMODB_TABLE_THEME_BASKET'] = 'TestThemeBasket'
        os.environ['DYNAMODB_TABLE_ROLLING_SCORES'] = 'TestRollingScores'
        os.environ['S3_BUCKET'] = 'test-bucket'
        
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        s3 = boto3.client('s3', region_name='us-east-1')
        
        # Create ThemeRegistry table
        dynamodb.create_table(
            TableName='TestThemeRegistry',
            KeySchema=[{'AttributeName': 'themeId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'themeId', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create ThemeBasket table
        dynamodb.create_table(
            TableName='TestThemeBasket',
            KeySchema=[
                {'AttributeName': 'themeId', 'KeyType': 'HASH'},
                {'AttributeName': 'ticker', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'themeId', 'AttributeType': 'S'},
                {'AttributeName': 'ticker', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create RollingScores table
        dynamodb.create_table(
            TableName='TestRollingScores',
            KeySchema=[{'AttributeName': 'ticker', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'ticker', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create Bucket
        s3.create_bucket(Bucket='test-bucket')
        
        yield dynamodb, s3

def test_theme_basket_worker(setup_aws):
    dynamodb, s3 = setup_aws
    
    # 1. Seed RollingScores
    rolling_table = dynamodb.Table('TestRollingScores')
    
    # SaaS match
    rolling_table.put_item(Item={
        'ticker': 'MSFT',
        'companyName': 'Microsoft Corp',
        'sector': 'Technology',
        'latestThesis': 'Excellent SaaS growth and enterprise cloud software dominance.',
        'latestVerdict': 'INVESTIGATE',
        'avgCompositeScore': decimal.Decimal('8.5'),
        'isInvestable': True
    })
    
    # AI match
    rolling_table.put_item(Item={
        'ticker': 'NVDA',
        'companyName': 'Nvidia Corporation',
        'sector': 'Technology',
        'latestThesis': 'Leading supplier of GPU hardware powering artificial intelligence.',
        'latestVerdict': 'INVESTIGATE',
        'avgCompositeScore': decimal.Decimal('9.2'),
        'isInvestable': False
    })
    
    # Unmatched stock
    rolling_table.put_item(Item={
        'ticker': 'KO',
        'companyName': 'Coca-Cola Co',
        'sector': 'Consumer Staples',
        'latestThesis': 'Stable dividends and traditional beverage brands.',
        'latestVerdict': 'MONITOR',
        'avgCompositeScore': decimal.Decimal('7.0'),
        'isInvestable': True
    })
    
    # Run the handler (should auto-seed default themes since registry is empty)
    response = themeBasketWorker.handler({}, {})
    
    assert response['status'] == 'SUCCESS'
    assert response['themesMatched'] == 4 # 4 default themes seeded
    assert response['totalMatches'] == 2 # NVDA matches AI, MSFT matches SaaS
    
    # Check ThemeBasket table entries
    basket_table = dynamodb.Table('TestThemeBasket')
    matches = basket_table.scan()['Items']
    
    assert len(matches) == 2
    
    nvda_match = next(m for m in matches if m['ticker'] == 'NVDA')
    assert nvda_match['themeId'] == 'ai-semiconductors'
    assert 'gpu' in nvda_match['matchedKeywords']
    assert nvda_match['isInvestable'] is False
    
    msft_match = next(m for m in matches if m['ticker'] == 'MSFT')
    assert msft_match['themeId'] == 'saas-cloud'
    assert 'saas' in msft_match['matchedKeywords']
    assert msft_match['isInvestable'] is True
    
    # Check S3 export file
    summary_obj = s3.get_object(Bucket='test-bucket', Key='dashboard/theme_baskets.json')
    summary = json.loads(summary_obj['Body'].read().decode('utf-8'))
    
    assert 'updatedAt' in summary
    assert 'baskets' in summary
    
    baskets = summary['baskets']
    assert 'saas-cloud' in baskets
    assert 'ai-semiconductors' in baskets
    
    saas_stocks = baskets['saas-cloud']['stocks']
    assert len(saas_stocks) == 1
    assert saas_stocks[0]['ticker'] == 'MSFT'
    
    ai_stocks = baskets['ai-semiconductors']['stocks']
    assert len(ai_stocks) == 1
    assert ai_stocks[0]['ticker'] == 'NVDA'

def test_custom_regex_theme_matching(setup_aws):
    dynamodb, s3 = setup_aws
    
    # Clean registry first
    reg_table = dynamodb.Table('TestThemeRegistry')
    for item in reg_table.scan()['Items']:
        reg_table.delete_item(Key={'themeId': item['themeId']})
        
    # Seed a custom theme with a regex keyword
    reg_table.put_item(Item={
        'themeId': 'telecom-theme',
        'name': 'Telecom',
        'description': 'Telecommunications companies',
        'keywords': ['r/\\b(telecom|telephony)\\b/']
    })
    
    rolling_table = dynamodb.Table('TestRollingScores')
    # Clean rolling scores
    for item in rolling_table.scan()['Items']:
        rolling_table.delete_item(Key={'ticker': item['ticker']})
        
    # T matches telecom
    rolling_table.put_item(Item={
        'ticker': 'T',
        'companyName': 'AT&T Inc',
        'sector': 'Communication Services',
        'latestThesis': 'Stable provider of cellular telephony and internet services.',
        'avgCompositeScore': decimal.Decimal('7.0'),
        'isInvestable': True
    })
    
    # KO does not match telecom
    rolling_table.put_item(Item={
        'ticker': 'KO',
        'companyName': 'Coca-Cola',
        'sector': 'Consumer Staples',
        'latestThesis': 'Beverage giant.',
        'avgCompositeScore': decimal.Decimal('7.5'),
        'isInvestable': True
    })
    
    response = themeBasketWorker.handler({}, {})
    assert response['status'] == 'SUCCESS'
    
    # Telecom theme should match T, KO should not match
    basket_table = dynamodb.Table('TestThemeBasket')
    matches = basket_table.scan()['Items']
    
    assert len(matches) == 1
    assert matches[0]['ticker'] == 'T'
    assert matches[0]['themeId'] == 'telecom-theme'
    assert 'r/\\b(telecom|telephony)\\b/' in matches[0]['matchedKeywords']
