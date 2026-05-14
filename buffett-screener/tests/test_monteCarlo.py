import os
import json
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3
import decimal

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../amplify/functions')))

import monteCarlo

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
        # Pre-populate table
        table = dynamodb.Table('TestStockScores')
        table.put_item(Item={
            'runId': '2026-W01',
            'ticker': 'AAPL',
            'compositeScore': decimal.Decimal('8.5'),
            'scoreMoat': decimal.Decimal('9')
        })
        yield dynamodb

def test_handler(setup_aws):
    dynamodb = setup_aws
    
    event = {
        'run_id': '2026-W01',
        'candidates': [
            {
                'ticker': 'AAPL',
                'composite_score': 8.5,
                'roe5yrAvg': 0.20,
                'netMargin': 0.15,
                'debtToEquity': 0.50,
                'fcfGrowth3yr': 0.10,
                'epsGrowth5yr': 0.15,
                'currentRatio': 1.5,
                'peRatio': 20.0,
                'scores': {'moat': 9, 'financial_health': 8, 'management': 8, 'simplicity': 9, 'margin_of_safety': 8}
            }
        ]
    }
    
    response = monteCarlo.handler(event, {})
    
    assert 'results' in response
    assert 'AAPL' in response['results']
    assert response['results']['AAPL']['n_runs'] == 500
    
    # Check DynamoDB
    table = dynamodb.Table('TestStockScores')
    item = table.get_item(Key={'runId': '2026-W01', 'ticker': 'AAPL'})['Item']
    
    assert 'mcP10' in item
    assert 'mcP90' in item
    assert 'mcProbInvestigate' in item
    assert 'mcConfidenceBand' in item
    assert item['mcP10'] < item['mcP90']
