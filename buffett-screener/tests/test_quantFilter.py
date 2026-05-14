import os
import json
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../amplify/functions')))

import quantFilter

@pytest.fixture
def setup_aws(env_setup):
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        s3 = boto3.client('s3', region_name='us-east-1')

        # Create Table
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

        # Create Bucket
        s3.create_bucket(Bucket='test-bucket')
        s3.put_object(
            Bucket='test-bucket',
            Key='metrics/test.json',
            Body=json.dumps([
                {
                    'ticker': 'AAPL', 
                    'name': 'Apple', 
                    'sector': 'Technology',
                    'roe5yrAvg': 0.20,
                    'netMargin': 0.15,
                    'debtToEquity': 0.50,
                    'fcfGrowth3yr': 0.10,
                    'epsGrowth5yr': 0.15,
                    'currentRatio': 1.5,
                    'peRatio': 20.0
                }
            ])
        )

        yield dynamodb, s3

def test_handler(setup_aws):
    dynamodb, s3 = setup_aws
    
    event = {'run_id': '2026-W01', 's3_metrics_key': 'metrics/test.json'}
    response = quantFilter.handler(event, {})
    
    assert 'candidates' in response
    assert len(response['candidates']) == 1
    assert response['candidates'][0]['ticker'] == 'AAPL'
    
    # Check if wrote to StockScores correctly
    table = dynamodb.Table('TestStockScores')
    items = table.scan()['Items']
    assert len(items) == 1
    assert items[0]['ticker'] == 'AAPL'
