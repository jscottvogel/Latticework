import os
import json
import decimal
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../amplify/functions')))

import aiScorer

@pytest.fixture
def setup_aws(env_setup):
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        dynamodb.create_table(
            TableName='TestStockScores',
            KeySchema=[
                {'AttributeName': 'runId', 'KeyType': 'HASH'},
                {'AttributeName': 'ticker', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'runId', 'AttributeType': 'S'},
                {'AttributeName': 'ticker', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        yield dynamodb

@patch('aiScorer.get_anthropic_key')
@patch('urllib.request.urlopen')
def test_handler(mock_urlopen, mock_get_key, setup_aws):
    dynamodb = setup_aws
    mock_get_key.return_value = 'TEST_KEY'
    
    # Fake response from Anthropic API
    fake_claude_response = {
        "content": [
            {
                "text": json.dumps({
                    "ticker": "AAPL",
                    "company_name": "Apple",
                    "composite_score": 8.5,
                    "scores": {
                        "moat": 9,
                        "financial_health": 8,
                        "management": 8,
                        "simplicity": 9,
                        "margin_of_safety": 8
                    },
                    "verdict": "INVESTIGATE",
                    "confidence": "High",
                    "one_line_thesis": "Strong moat.",
                    "key_risks": ["Competition"],
                    "red_flags": [],
                    "revenue_exposure": {
                        "hardware": 0.60,
                        "china": 0.20
                    }
                })
            }
        ],
        "usage": {"input_tokens": 1000, "output_tokens": 500}
    }
    
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(fake_claude_response).encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    
    event = {
        'run_id': '2026-W01',
        'candidates': [
            {
                'ticker': 'AAPL',
                'company_name': 'Apple',
                'metrics': {
                    'peRatio': 20,
                    'description': 'Apple builds premium hardware and does business in China.'
                },
                'news_summary': 'Good news'
            }
        ]
    }
    
    response = aiScorer.handler(event, {})
    
    assert 'scores' in response
    assert len(response['scores']) == 1
    assert response['scores'][0]['composite_score'] == pytest.approx(8.45)
    assert response['scores'][0]['ai_reported_composite'] == 8.5
    assert response['scores'][0]['verdict'] == 'INVESTIGATE'
    assert response['scores'][0]['metrics']['peRatio'] == 20
    assert response['total_cost_usd'] > 0
    
    # Check DynamoDB
    table = dynamodb.Table('TestStockScores')
    items = table.scan()['Items']
    assert len(items) == 1
    assert items[0]['ticker'] == 'AAPL'
    assert items[0]['verdict'] == 'INVESTIGATE'
    assert items[0]['compositeScore'] == decimal.Decimal('8.45')
    assert items[0]['aiReportedComposite'] == decimal.Decimal('8.5')
    
    # Verify revenueExposure is saved
    assert 'revenueExposure' in items[0]
    exposure_dict = json.loads(items[0]['revenueExposure'])
    assert exposure_dict['hardware'] == 0.60
    assert exposure_dict['china'] == 0.20

def test_verify_revenue_exposure():
    # Test cases for verify_revenue_exposure
    
    # Case 1: Matches found - no flags added
    result = {
        'revenue_exposure': {
            'hardware': 0.60,
            'china': 0.20,
            'small_exp': 0.05 # should be ignored (< 10%)
        },
        'red_flags': []
    }
    metrics = {
        'description': 'Designs premium hardware consumer electronics.',
        'sector': 'Technology'
    }
    news = 'Recent events in China impact supply chains.'
    
    aiScorer.verify_revenue_exposure('AAPL', result, metrics, news)
    assert len(result['red_flags']) == 0
    
    # Case 2: Mismatched exposure - should add red flag warning
    result2 = {
        'revenue_exposure': {
            'cloud': 0.50,
            'russia': 0.30
        },
        'red_flags': []
    }
    metrics2 = {
        'description': 'Traditional retail stores selling apparel.',
        'sector': 'Consumer Cyclical'
    }
    news2 = 'Opening new outlets in New York.'
    
    aiScorer.verify_revenue_exposure('TGT', result2, metrics2, news2)
    assert len(result2['red_flags']) == 2
    assert "Mismatched revenue exposure: 'cloud' not mentioned in overview/news" in result2['red_flags']
    assert "Mismatched revenue exposure: 'russia' not mentioned in overview/news" in result2['red_flags']
