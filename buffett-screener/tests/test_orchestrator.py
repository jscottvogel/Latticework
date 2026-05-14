import os
import json
import decimal
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../amplify/functions')))

import orchestrator

@pytest.fixture
def setup_aws(env_setup):
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        s3 = boto3.client('s3', region_name='us-east-1')
        sns = boto3.client('sns', region_name='us-east-1')

        # Create Tables
        dynamodb.create_table(
            TableName='TestWeeklyRuns',
            KeySchema=[{'AttributeName': 'runId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'runId', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        dynamodb.create_table(
            TableName='TestRollingScores',
            KeySchema=[{'AttributeName': 'ticker', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'ticker', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )

        # Create Bucket
        s3.create_bucket(Bucket='test-bucket')
        
        # Create Topic
        sns.create_topic(Name='test-alert')

        yield dynamodb, s3, sns

def test_get_run_id():
    run_id = orchestrator.get_run_id()
    assert run_id.startswith('202')
    assert '-W' in run_id

@patch('orchestrator.invoke_lambda')
def test_handler_dry_run(mock_invoke, setup_aws):
    dynamodb, s3, sns = setup_aws
    
    mock_invoke.side_effect = [
        {'metrics': [{'ticker': 'AAPL'}], 's3_key': 'test.json'}, # DATA_FETCH
        {'candidates': [{'ticker': 'AAPL'}]} # QUANT_FILTER
    ]
    
    response = orchestrator.handler({'dry_run': True}, {})
    
    assert response['status'] == 'DRY_RUN_COMPLETE'
    
    table = dynamodb.Table('TestWeeklyRuns')
    runs = table.scan()['Items']
    assert len(runs) == 1
    assert runs[0]['status'] == 'COMPLETE'
    assert runs[0]['errorMessage'] == 'DRY RUN'

@patch('orchestrator.invoke_lambda')
def test_handler_full_run(mock_invoke, setup_aws):
    dynamodb, s3, sns = setup_aws
    
    mock_invoke.side_effect = [
        {'metrics': [{'ticker': 'AAPL'}], 's3_key': 'test.json'}, # DATA_FETCH
        {'candidates': [{'ticker': 'AAPL', 'companyName': 'Apple'}]}, # QUANT_FILTER
        {'news': {'AAPL': 'Good news'}}, # NEWS_FETCH
        {'scores': [{'ticker': 'AAPL', 'companyName': 'Apple', 'compositeScore': 8.5, 'verdict': 'INVESTIGATE'}], 'total_cost_usd': 0.1}, # AI_SCORER
        {'status': 'ok'} # MONTE_CARLO
    ]
    
    response = orchestrator.handler({}, {})
    
    assert response['status'] == 'COMPLETE'
    
    # Check Weekly Runs
    runs_table = dynamodb.Table('TestWeeklyRuns')
    runs = runs_table.scan()['Items']
    assert runs[0]['status'] == 'COMPLETE'
    assert runs[0]['totalCostUsd'] == decimal.Decimal('0.1')
    assert runs[0]['stocksScreened'] == 1
    
    # Check Rolling Scores
    rolling_table = dynamodb.Table('TestRollingScores')
    rolling = rolling_table.scan()['Items']
    assert len(rolling) == 1
    assert rolling[0]['ticker'] == 'AAPL'
    assert rolling[0]['avgCompositeScore'] == decimal.Decimal('8.5')
    assert rolling[0]['investigateCount'] == 1
    assert rolling[0]['isInvestable'] == False # needs 3 appearances
    
    # Check S3 Dashboard
    objs = s3.list_objects_v2(Bucket='test-bucket')['Contents']
    assert len(objs) == 2 # latest.json and run_id.json

@patch('orchestrator.invoke_lambda')
def test_handler_failure(mock_invoke, setup_aws):
    dynamodb, s3, sns = setup_aws
    
    mock_invoke.side_effect = Exception("Test Failure")
    
    with pytest.raises(Exception):
        orchestrator.handler({}, {})
        
    runs_table = dynamodb.Table('TestWeeklyRuns')
    runs = runs_table.scan()['Items']
    assert runs[0]['status'] == 'FAILED'
    assert runs[0]['errorMessage'] == 'Test Failure'
