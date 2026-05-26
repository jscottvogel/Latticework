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

@patch('dataFetch.get_secret')
@patch('urllib.request.urlopen')
def test_handler_stateful_queue(mock_urlopen, mock_get_key, setup_aws):
    dynamodb, s3 = setup_aws
    mock_get_key.return_value = "TEST_API_KEY"
    
    # Mock URL responses
    def urlopen_side_effect(req, *args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "Symbol": "AAPL",
            "Name": "Apple Inc.",
            "PERatio": "20"
        }).encode('utf-8')
        return MagicMock(__enter__=MagicMock(return_value=mock_resp))
        
    mock_urlopen.side_effect = urlopen_side_effect
    
    # Write a pre-existing cache file for S&P 500 tickers
    s3.put_object(
        Bucket='test-bucket',
        Key='tickers-cache/sp500_v2.json',
        Body=json.dumps({"tickers": ["AAPL", "MSFT", "GOOG"]})
    )
    
    # Write an initial queue state where MSFT failed and AAPL is pending
    initial_queue = {
        "AAPL": {"lastFetched": "2026-05-24T12:00:00Z", "lastStatus": "SUCCESS"},
        "MSFT": {"lastFetched": "2026-05-23T12:00:00Z", "lastStatus": "FAILED"},
        "GOOG": {"lastFetched": "2026-05-25T12:00:00Z", "lastStatus": "SUCCESS"}
    }
    s3.put_object(
        Bucket='test-bucket',
        Key='tickers-cache/fetch-queue_v1.json',
        Body=json.dumps(initial_queue)
    )
    
    # Run dataFetch with NO tickers specified, with limit = 3
    # This should trigger stateful queue selection
    with patch.dict(os.environ, {'LIMIT_SP500_TICKERS': '3'}):
        event = {'run_id': '2026-W02'}
        response = dataFetch.handler(event, {})
        
    # Ticker selection:
    # - previous_top_tickers: [] (none)
    # - target_count: 3
    # - failed tickers: MSFT (status = FAILED) -> added first
    # - remaining sorted by lastFetched: AAPL (24th) is older than GOOG (25th)
    # - So tickers to fetch should be: ['MSFT', 'AAPL', 'GOOG']
    
    metrics = response['metrics']
    assert len(metrics) == 3
    assert metrics[0]['ticker'] == 'MSFT'
    assert metrics[1]['ticker'] == 'AAPL'
    assert metrics[2]['ticker'] == 'GOOG'
    
    # Verify S3 fetch queue is updated and saved
    obj = s3.get_object(Bucket='test-bucket', Key='tickers-cache/fetch-queue_v1.json')
    updated_queue = json.loads(obj['Body'].read().decode('utf-8'))
    
    assert updated_queue['MSFT']['lastStatus'] == 'SUCCESS'  # because the mock urlopen returned Name "Apple Inc."
    assert updated_queue['MSFT']['lastFetched'] is not None


@mock_aws
def test_get_secret_json_dict_key():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    client.create_secret(Name='/buffett-screener/alpha-vantage-key', SecretString='{"key": "json_dict_key"}')
    dataFetch._ALPHA_VANTAGE_KEY = None
    key = dataFetch.get_secret('/buffett-screener/alpha-vantage-key')
    assert key == "json_dict_key"


@mock_aws
def test_get_secret_json_dict_apikey():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    client.create_secret(Name='/buffett-screener/alpha-vantage-key', SecretString='{"apikey": "json_dict_apikey"}')
    dataFetch._ALPHA_VANTAGE_KEY = None
    key = dataFetch.get_secret('/buffett-screener/alpha-vantage-key')
    assert key == "json_dict_apikey"


@mock_aws
def test_get_secret_json_dict_apiKey_camelCase():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    client.create_secret(Name='/buffett-screener/alpha-vantage-key', SecretString='{"apiKey": "json_dict_apiKey_camel"}')
    dataFetch._ALPHA_VANTAGE_KEY = None
    key = dataFetch.get_secret('/buffett-screener/alpha-vantage-key')
    assert key == "json_dict_apiKey_camel"


@mock_aws
def test_get_secret_json_string():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    client.create_secret(Name='/buffett-screener/alpha-vantage-key', SecretString='"json_string_key"')
    dataFetch._ALPHA_VANTAGE_KEY = None
    key = dataFetch.get_secret('/buffett-screener/alpha-vantage-key')
    assert key == "json_string_key"


@mock_aws
def test_get_secret_raw_string():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    client.create_secret(Name='/buffett-screener/alpha-vantage-key', SecretString='raw_plaintext_key_123')
    dataFetch._ALPHA_VANTAGE_KEY = None
    key = dataFetch.get_secret('/buffett-screener/alpha-vantage-key')
    assert key == "raw_plaintext_key_123"


@mock_aws
def test_get_secret_malformed_json_dict():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    client.create_secret(Name='/buffett-screener/alpha-vantage-key', SecretString='{key:15JJCDS4OY9J7QSG}')
    dataFetch._ALPHA_VANTAGE_KEY = None
    key = dataFetch.get_secret('/buffett-screener/alpha-vantage-key')
    assert key == "15JJCDS4OY9J7QSG"



