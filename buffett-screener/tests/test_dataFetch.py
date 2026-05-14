import os
import json
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../amplify/functions')))

import dataFetch

@pytest.fixture
def setup_aws(env_setup):
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        s3 = boto3.client('s3', region_name='us-east-1')

        # Create Table
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

@patch('dataFetch.get_secret')
@patch('urllib.request.urlopen')
def test_handler(mock_urlopen, mock_get_key, setup_aws):
    dynamodb, s3 = setup_aws
    mock_get_key.return_value = "TEST_API_KEY"
    
    # Mock SP500 URL and Overview URL
    def urlopen_side_effect(req, *args, **kwargs):
        url = req.full_url if hasattr(req, 'full_url') else req
        mock_resp = MagicMock()
        if 'function=SP500' in url:
            mock_resp.read.return_value = json.dumps({
                "data": [
                    {"symbol": "AAPL", "name": "Apple", "sector": "Tech"}
                ]
            }).encode('utf-8')
        elif 'function=OVERVIEW' in url:
            mock_resp.read.return_value = json.dumps({
                "Symbol": "AAPL",
                "ReturnOnEquityTTM": "0.20",
                "ProfitMargin": "0.15",
                "OperatingMarginTTM": "0.15",
                "QuarterlyEarningsGrowthYOY": "0.10",
                "QuarterlyRevenueGrowthYOY": "0.10",
                "PERatio": "20"
            }).encode('utf-8')
        elif 'function=INCOME_STATEMENT' in url:
            mock_resp.read.return_value = json.dumps({
                "annualReports": [
                    {"netIncome": "100"},
                    {"netIncome": "90"}
                ]
            }).encode('utf-8')
        elif 'function=BALANCE_SHEET' in url:
            mock_resp.read.return_value = json.dumps({
                "annualReports": [
                    {"totalAssets": "1000", "totalLiabilities": "500", "totalShareholderEquity": "500"}
                ]
            }).encode('utf-8')
        elif 'function=CASH_FLOW' in url:
            mock_resp.read.return_value = json.dumps({
                "annualReports": [
                    {"operatingCashflow": "200", "capitalExpenditures": "50"},
                    {"operatingCashflow": "180", "capitalExpenditures": "40"}
                ]
            }).encode('utf-8')
        else:
            mock_resp.read.return_value = json.dumps({}).encode('utf-8')
            
        return MagicMock(__enter__=MagicMock(return_value=mock_resp))
        
    mock_urlopen.side_effect = urlopen_side_effect
    
    event = {'run_id': '2026-W01', 'tickers': ['AAPL']}
    response = dataFetch.handler(event, {})
    
    assert 's3_key' in response
    assert response['s3_key'].startswith('raw-financials/2026-W01')
    assert len(response['metrics']) == 1
    
    # Check S3
    objs = s3.list_objects_v2(Bucket='test-bucket')['Contents']
    assert len(objs) == 1
    
    # Check DynamoDB
    table = dynamodb.Table('TestRawFinancials')
    items = table.scan()['Items']
    assert len(items) == 1
    assert items[0]['ticker'] == 'AAPL'
