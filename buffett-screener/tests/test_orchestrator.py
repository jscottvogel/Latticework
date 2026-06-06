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
    assert '-D' in run_id

@patch('orchestrator.invoke_lambda')
def test_handler_dry_run(mock_invoke, setup_aws):
    dynamodb, s3, sns = setup_aws
    
    mock_invoke.side_effect = [
        {'metrics': [{'ticker': 'AAPL'}], 's3_key': 'test.json'}, # DATA_FETCH
        {'candidates': [{'ticker': 'AAPL'}]} # QUANT_FILTER
    ]
    
    response = orchestrator.handler({'dry_run': True, 'force': True}, {})
    
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
    
    response = orchestrator.handler({'force': True}, {})
    
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
        orchestrator.handler({'force': True}, {})
        
    runs_table = dynamodb.Table('TestWeeklyRuns')
    runs = runs_table.scan()['Items']
    assert runs[0]['status'] == 'FAILED'
    assert runs[0]['errorMessage'] == 'Test Failure'

def test_update_rolling_scores_28_days(setup_aws):
    dynamodb, s3, sns = setup_aws
    runs_table = dynamodb.Table('TestWeeklyRuns')
    scores_table = dynamodb.Table('TestStockScores')
    rolling_table = dynamodb.Table('TestRollingScores')
    
    # Seed 27 completed runs in the database plus the 28th run
    for i in range(1, 28):
        run_id = f'2026-D{i:03d}'
        runs_table.put_item(Item={
            'runId': run_id,
            'status': 'COMPLETE',
            'runDate': f'2026-05-{i:02d}'
        })
        
        # AAPL is always in the top 10.
        # MSFT is only in runs 2 to 28 (27 appearances).
        scores_table.put_item(Item={
            'runId': run_id,
            'ticker': 'AAPL',
            'companyName': 'Apple Inc.',
            'sector': 'Technology',
            'compositeScore': decimal.Decimal('9.0'),
            'verdict': 'INVESTIGATE',
            'oneLineThesis': 'Great company.',
            'rankThisWeek': 1
        })
        
        if i > 1:
            scores_table.put_item(Item={
                'runId': run_id,
                'ticker': 'MSFT',
                'companyName': 'Microsoft Corp.',
                'sector': 'Technology',
                'compositeScore': decimal.Decimal('8.5'),
                'verdict': 'INVESTIGATE',
                'oneLineThesis': 'Solid enterprise.',
                'rankThisWeek': 2
            })
            
    # Now call update_rolling_scores for the 28th run: '2026-D028'
    current_scores = [
        {
            'ticker': 'AAPL',
            'company_name': 'Apple Inc.',
            'composite_score': 9.0,
            'verdict': 'INVESTIGATE',
            'one_line_thesis': 'Great company.',
            'rank_this_week': 1
        },
        {
            'ticker': 'MSFT',
            'company_name': 'Microsoft Corp.',
            'composite_score': 8.5,
            'verdict': 'INVESTIGATE',
            'one_line_thesis': 'Solid enterprise.',
            'rank_this_week': 2
        }
    ]
    
    orchestrator.update_rolling_scores('2026-D028', current_scores, candidates=[])
    
    # Check results in TestRollingScores
    rolling_items = rolling_table.scan()['Items']
    rolling_map = {item['ticker']: item for item in rolling_items}
    
    assert 'AAPL' in rolling_map
    assert 'MSFT' in rolling_map
    
    # AAPL: 28 appearances -> isInvestable = True
    assert rolling_map['AAPL']['appearancesLast4Weeks'] == 28
    assert rolling_map['AAPL']['isInvestable'] is True
    assert len(rolling_map['AAPL']['scoreHistory']) == 28
    
    # MSFT: 27 appearances -> isInvestable = False
    assert rolling_map['MSFT']['appearancesLast4Weeks'] == 27
    assert rolling_map['MSFT']['isInvestable'] is False
    assert len(rolling_map['MSFT']['scoreHistory']) == 27


def test_is_us_holiday_or_weekend():
    from datetime import datetime
    
    # Weekends
    assert orchestrator.is_us_holiday_or_weekend(datetime(2026, 5, 23)) is True # Saturday
    assert orchestrator.is_us_holiday_or_weekend(datetime(2026, 5, 24)) is True # Sunday
    
    # Weekdays
    assert orchestrator.is_us_holiday_or_weekend(datetime(2026, 5, 26)) is False # Normal Tuesday
    
    # Holidays (2026)
    assert orchestrator.is_us_holiday_or_weekend(datetime(2026, 1, 1)) is True   # New Year
    assert orchestrator.is_us_holiday_or_weekend(datetime(2026, 5, 25)) is True  # Memorial Day
    assert orchestrator.is_us_holiday_or_weekend(datetime(2026, 7, 4)) is True   # Independence Day
    assert orchestrator.is_us_holiday_or_weekend(datetime(2026, 7, 3)) is True   # Independence Day observed
    assert orchestrator.is_us_holiday_or_weekend(datetime(2026, 11, 26)) is True # Thanksgiving


@patch('orchestrator.invoke_lambda')
def test_handler_skips_on_weekend(mock_invoke, setup_aws):
    dynamodb, s3, sns = setup_aws
    
    from datetime import datetime, timezone
    mock_datetime = MagicMock(wraps=datetime)
    mock_datetime.now.return_value = datetime(2026, 5, 23, 14, 0, 0, tzinfo=timezone.utc)
    
    with patch('orchestrator.datetime', mock_datetime):
        response = orchestrator.handler({}, {})
        
    assert response == {'status': 'SKIPPED_HOLIDAY_OR_WEEKEND'}
    
    table = dynamodb.Table('TestWeeklyRuns')
    runs = table.scan()['Items']
    assert len(runs) == 1
    assert runs[0]['status'] == 'SKIPPED'
    assert 'holiday or weekend' in runs[0]['errorMessage']
    assert mock_invoke.call_count == 0


@patch('orchestrator.invoke_lambda')
def test_handler_runs_when_forced(mock_invoke, setup_aws):
    dynamodb, s3, sns = setup_aws
    
    mock_invoke.side_effect = [
        {'metrics': [{'ticker': 'AAPL'}], 's3_key': 'test.json'}, # DATA_FETCH
        {'candidates': [{'ticker': 'AAPL'}]} # QUANT_FILTER
    ]
    
    from datetime import datetime, timezone
    mock_datetime = MagicMock(wraps=datetime)
    mock_datetime.now.return_value = datetime(2026, 5, 23, 14, 0, 0, tzinfo=timezone.utc)
    
    with patch('orchestrator.datetime', mock_datetime):
        response = orchestrator.handler({'dry_run': True, 'force': True}, {})
        
    assert response['status'] == 'DRY_RUN_COMPLETE'
    
    table = dynamodb.Table('TestWeeklyRuns')
    runs = table.scan()['Items']
    assert len(runs) == 1
    assert runs[0]['status'] == 'COMPLETE'


def test_completed_runs_sorting_chronological(setup_aws):
    dynamodb, s3, sns = setup_aws
    runs_table = dynamodb.Table('TestWeeklyRuns')
    
    # '2026-W21' is alphabetically greater than '2026-D156' ('W' > 'D'),
    # but chronologically '2026-D156' is later (June 5 vs May 22).
    runs_table.put_item(Item={
        'runId': '2026-W21',
        'runDate': '2026-05-22',
        'createdAt': '2026-05-22T17:00:00.000000Z',
        'status': 'COMPLETE'
    })
    runs_table.put_item(Item={
        'runId': '2026-D156',
        'runDate': '2026-06-05',
        'createdAt': '2026-06-05T14:00:00.000000Z',
        'status': 'COMPLETE'
    })
    # Seed a third run with no createdAt to test fallback to runDate
    runs_table.put_item(Item={
        'runId': '2026-D155',
        'runDate': '2026-06-04',
        'status': 'COMPLETE'
    })
    
    response = runs_table.scan(
        FilterExpression="#s = :status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":status": "COMPLETE"}
    )
    completed_runs = response.get('Items', [])
    
    # Sort them using the exact logic from orchestrator.py
    completed_runs.sort(key=lambda x: x.get('createdAt', x.get('runDate', '')), reverse=True)
    
    sorted_ids = [r['runId'] for r in completed_runs]
    assert sorted_ids == ['2026-D156', '2026-D155', '2026-W21']



