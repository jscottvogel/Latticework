import os
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
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
        s3.create_bucket(Bucket='test-bucket')
        yield dynamodb, s3

@patch('urllib.request.urlopen')
def test_get_sp500_tickers_fallback_expired_cache(mock_urlopen, setup_aws):
    _, s3 = setup_aws
    
    # 1. Seed the S3 cache with mock tickers
    s3.put_object(
        Bucket='test-bucket',
        Key='tickers-cache/sp500_v2.json',
        Body=json.dumps({"tickers": ["AAPL", "MSFT", "GOOG"]})
    )
    
    # 2. Mock urllib to throw an exception (Wikipedia down/blocking)
    mock_urlopen.side_effect = Exception("HTTP 403 Forbidden")
    
    # 3. Mock datetime.now to return a date 10 days in the future relative to the cache file creation
    # (Since s3.put_object creates the file now, a future date makes the cache expired)
    future_time = datetime.now(timezone.utc) + timedelta(days=10)
    
    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return future_time
            
    with patch('dataFetch.datetime', MockDatetime):
        tickers = dataFetch.get_sp500_tickers(s3, 'test-bucket')
        
    # 4. Verify fallback worked and returned the cached tickers despite Wikipedia failure
    assert tickers == ["AAPL", "MSFT", "GOOG"]
