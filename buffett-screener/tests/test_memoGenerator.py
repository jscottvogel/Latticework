import json
import os
import pytest
import boto3
import decimal
from unittest.mock import patch, MagicMock
from moto import mock_aws

# Import handler and helper from memoGenerator
import memoGenerator

@pytest.fixture
def env_setup():
    os.environ['DYNAMODB_TABLE_STOCK_SCORES'] = 'TestStockScores'
    os.environ['DYNAMODB_TABLE_RAW_FINANCIALS'] = 'TestRawFinancials'
    os.environ['S3_BUCKET'] = 'test-bucket'
    yield
    # Clean up
    for var in ['DYNAMODB_TABLE_STOCK_SCORES', 'DYNAMODB_TABLE_RAW_FINANCIALS', 'S3_BUCKET']:
        if var in os.environ:
            del os.environ[var]

@pytest.fixture
def setup_aws(env_setup):
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        s3 = boto3.client('s3', region_name='us-east-1')
        
        # Create Tables
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
        
        dynamodb.create_table(
            TableName='TestRawFinancials',
            KeySchema=[
                {'AttributeName': 'ticker', 'KeyType': 'HASH'},
                {'AttributeName': 'runId', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'ticker', 'AttributeType': 'S'},
                {'AttributeName': 'runId', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create Bucket
        s3.create_bucket(Bucket='test-bucket')
        
        yield dynamodb, s3

@patch('memoGenerator._call_anthropic_api')
@patch('memoGenerator.get_anthropic_key')
def test_memo_generator_success(mock_get_key, mock_call_api, setup_aws):
    dynamodb, s3 = setup_aws
    mock_get_key.return_value = 'test-key'
    mock_call_api.return_value = "# Buffett-Style Investment Memo: AAPL\n\nThis is a mock memo body."
    
    # 1. Seed data into DynamoDB StockScores
    scores_table = dynamodb.Table('TestStockScores')
    scores_table.put_item(Item={
        'runId': '2026-W01',
        'ticker': 'AAPL',
        'companyName': 'Apple Inc.',
        'sector': 'Technology',
        'scoreMoat': decimal.Decimal('8.5'),
        'scoreFinancialHealth': decimal.Decimal('9.0'),
        'scoreManagement': decimal.Decimal('8.0'),
        'scoreSimplicity': decimal.Decimal('7.5'),
        'scoreMarginOfSafety': decimal.Decimal('7.0'),
        'compositeScore': decimal.Decimal('8.0'),
        'verdict': 'INVESTIGATE',
        'confidence': 'HIGH',
        'oneLineThesis': 'Consistent compounder with high product loyalty.',
        'keyRisks': ['Regulatory pressure', 'Hardware saturation'],
        'redFlags': [],
        'revenueExposure': '{"hardware": 0.6, "services": 0.4}'
    })
    
    # 2. Seed data into DynamoDB RawFinancials
    financials_table = dynamodb.Table('TestRawFinancials')
    financials_table.put_item(Item={
        'ticker': 'AAPL',
        'runId': '2026-W01',
        'description': 'Designs consumer electronics and services.'
    })
    
    # 3. Call handler
    event = {
        'ticker': 'AAPL',
        'run_id': '2026-W01'
    }
    
    response = memoGenerator.handler(event, {})
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'SUCCESS'
    assert body['memoPath'] == 'dashboard/memos/2026-W01/AAPL.md'
    
    # 4. Verify S3 file content
    obj = s3.get_object(Bucket='test-bucket', Key='dashboard/memos/2026-W01/AAPL.md')
    s3_content = obj['Body'].read().decode('utf-8')
    assert "This is a mock memo body." in s3_content
    
    # 5. Verify Meta-Prompt structure includes crucial variables passed to Claude
    mock_call_api.assert_called_once()
    prompt_sent = mock_call_api.call_args[0][1]
    assert "Apple Inc." in prompt_sent
    assert "Technology" in prompt_sent
    assert "8.5" in prompt_sent
    assert "9.0" in prompt_sent
    assert "Consistent compounder" in prompt_sent
