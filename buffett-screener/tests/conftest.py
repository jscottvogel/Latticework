import os
import pytest

@pytest.fixture(autouse=True)
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

@pytest.fixture
def env_setup():
    os.environ['DYNAMODB_TABLE_WEEKLY_RUNS'] = 'TestWeeklyRuns'
    os.environ['DYNAMODB_TABLE_STOCK_SCORES'] = 'TestStockScores'
    os.environ['DYNAMODB_TABLE_ROLLING_SCORES'] = 'TestRollingScores'
    os.environ['DYNAMODB_TABLE_RAW_FINANCIALS'] = 'TestRawFinancials'
    os.environ['S3_BUCKET'] = 'test-bucket'
    os.environ['SNS_ALERT_ARN'] = 'arn:aws:sns:us-east-1:123456789012:test-alert'
    
    os.environ['DATA_FETCH_FUNCTION_NAME'] = 'TestDataFetch'
    os.environ['QUANT_FILTER_FUNCTION_NAME'] = 'TestQuantFilter'
    os.environ['NEWS_FETCH_FUNCTION_NAME'] = 'TestNewsFetch'
    os.environ['AI_SCORER_FUNCTION_NAME'] = 'TestAiScorer'
    os.environ['MONTE_CARLO_FUNCTION_NAME'] = 'TestMonteCarlo'
