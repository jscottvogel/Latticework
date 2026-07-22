import os
import json
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_aws
import boto3
from datetime import datetime, timezone, timedelta
import decimal

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../amplify/functions')))

import backtestValidator

@pytest.fixture
def setup_aws(env_setup):
    with mock_aws():
        # Override table env vars for testing
        os.environ['DYNAMODB_TABLE_STOCK_SCORES'] = 'TestStockScores'
        os.environ['DYNAMODB_TABLE_SCORE_OUTCOMES'] = 'TestScoreOutcomes'
        os.environ['S3_BUCKET'] = 'test-bucket'
        os.environ['ALPHA_VANTAGE_TIER'] = 'premium'
        
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        s3 = boto3.client('s3', region_name='us-east-1')
        
        # Create StockScores table
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
        
        # Create ScoreOutcomes table
        dynamodb.create_table(
            TableName='TestScoreOutcomes',
            KeySchema=[
                {'AttributeName': 'runId', 'KeyType': 'HASH'},
                {'AttributeName': 'tickerHorizon', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'runId', 'AttributeType': 'S'},
                {'AttributeName': 'tickerHorizon', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create Bucket
        s3.create_bucket(Bucket='test-bucket')
        
        yield dynamodb, s3

@patch('backtestValidator.get_secret')
@patch('urllib.request.urlopen')
def test_handler(mock_urlopen, mock_get_key, setup_aws):
    dynamodb, s3 = setup_aws
    mock_get_key.return_value = "TEST_API_KEY"
    
    # Calculate dates
    today = datetime.now(timezone.utc).date()
    
    # AAPL snapshot: 95 days ago (matures for 30 and 90, not 365)
    snap_aapl = today - timedelta(days=95)
    snap_aapl_str = snap_aapl.strftime("%Y-%m-%d")
    
    mat_30_aapl = snap_aapl + timedelta(days=30)
    mat_30_aapl_str = mat_30_aapl.strftime("%Y-%m-%d")
    
    mat_90_aapl = snap_aapl + timedelta(days=90)
    mat_90_aapl_str = mat_90_aapl.strftime("%Y-%m-%d")
    
    # MSFT snapshot: 10 days ago (does not mature for any horizon)
    snap_msft = today - timedelta(days=10)
    snap_msft_str = snap_msft.strftime("%Y-%m-%d")
    
    # Seed StockScores
    scores_table = dynamodb.Table('TestStockScores')
    
    # AAPL score (investigate, high confidence)
    scores_table.put_item(Item={
        'runId': '2026-W01',
        'ticker': 'AAPL',
        'createdAt': snap_aapl.isoformat() + 'Z',
        'scoreMoat': decimal.Decimal('9'),
        'scoreFinancialHealth': decimal.Decimal('8'),
        'scoreManagement': decimal.Decimal('8'),
        'scoreSimplicity': decimal.Decimal('9'),
        'scoreMarginOfSafety': decimal.Decimal('8'),
        'compositeScore': decimal.Decimal('8.45'),
        'verdict': 'INVESTIGATE',
        'confidence': 'HIGH'
    })
    
    # MSFT score (recent, not matured)
    scores_table.put_item(Item={
        'runId': '2026-W10',
        'ticker': 'MSFT',
        'createdAt': snap_msft.isoformat() + 'Z',
        'scoreMoat': decimal.Decimal('8'),
        'scoreFinancialHealth': decimal.Decimal('9'),
        'scoreManagement': decimal.Decimal('7'),
        'scoreSimplicity': decimal.Decimal('8'),
        'scoreMarginOfSafety': decimal.Decimal('7'),
        'compositeScore': decimal.Decimal('8.0'),
        'verdict': 'INVESTIGATE',
        'confidence': 'HIGH'
    })
    
    # Mock daily adjusted series responses
    def urlopen_side_effect(req, *args, **kwargs):
        url = req.full_url if hasattr(req, 'full_url') else req
        mock_resp = MagicMock()
        
        # AAPL series
        if 'symbol=AAPL' in url:
            mock_resp.read.return_value = json.dumps({
                "Time Series (Daily)": {
                    snap_aapl_str: {"5. adjusted close": "150.0"},
                    mat_30_aapl_str: {"5. adjusted close": "165.0"}, # +10% return
                    mat_90_aapl_str: {"5. adjusted close": "180.0"}, # +20% return
                }
            }).encode('utf-8')
        # SPY series
        elif 'symbol=SPY' in url:
            mock_resp.read.return_value = json.dumps({
                "Time Series (Daily)": {
                    snap_aapl_str: {"5. adjusted close": "400.0"},
                    mat_30_aapl_str: {"5. adjusted close": "420.0"}, # +5% return
                    mat_90_aapl_str: {"5. adjusted close": "448.0"}, # +12% return
                }
            }).encode('utf-8')
        else:
            mock_resp.read.return_value = json.dumps({
                "Time Series (Daily)": {}
            }).encode('utf-8')
            
        return MagicMock(__enter__=MagicMock(return_value=mock_resp))
        
    mock_urlopen.side_effect = urlopen_side_effect
    
    # Run backtest validator handler
    response = backtestValidator.handler({}, {})
    assert response['status'] == 'SUCCESS'
    # Should have processed 2 outcomes for AAPL (30 and 90 day horizons)
    assert response['processed'] == 2
    
    # Check outcomes in table
    outcomes_table = dynamodb.Table('TestScoreOutcomes')
    outcomes = outcomes_table.scan()['Items']
    
    assert len(outcomes) == 2
    
    # Sort outcomes by horizon
    outcomes.sort(key=lambda x: int(x['horizonDays']))
    
    # 30-Day AAPL return
    o30 = outcomes[0]
    assert o30['ticker'] == 'AAPL'
    assert o30['horizonDays'] == 30
    assert o30['scoreSnapshotDate'] == snap_aapl_str
    assert o30['stockReturnPct'] == decimal.Decimal('0.1')  # (165-150)/150
    assert o30['spReturnPct'] == decimal.Decimal('0.05')    # (420-400)/400
    assert o30['excessReturnPct'] == decimal.Decimal('0.05') # 0.1 - 0.05
    
    # 90-Day AAPL return
    o90 = outcomes[1]
    assert o90['ticker'] == 'AAPL'
    assert o90['horizonDays'] == 90
    assert o90['stockReturnPct'] == decimal.Decimal('0.2')   # (180-150)/150
    assert o90['spReturnPct'] == decimal.Decimal('0.12')     # (448-400)/400
    assert o90['excessReturnPct'] == decimal.Decimal('0.08')  # 0.2 - 0.12
    
    # Check validation summary export in S3
    summary_obj = s3.get_object(Bucket='test-bucket', Key='dashboard/validation_summary.json')
    summary = json.loads(summary_obj['Body'].read().decode('utf-8'))
    
    assert 'updatedAt' in summary
    assert 'horizons' in summary
    assert summary['horizons']['30']['count'] == 1
    assert summary['horizons']['30']['calibration']['investigateHighCount'] == 1
    assert summary['horizons']['30']['calibration']['investigateHighBeatCount'] == 1
    assert summary['horizons']['30']['calibration']['investigateHighBeatRate'] == 1.0
    
    # Assert score tiering is present
    assert 'tiers' in summary['horizons']['30']
    tiers30 = summary['horizons']['30']['tiers']
    assert len(tiers30) == 4
    # AAPL has composite score 8.45, so it should be in Tier 1 (Excellent)
    t1 = next(t for t in tiers30 if t['tier'] == 'tier1')
    assert t1['count'] == 1
    assert t1['beatCount'] == 1
    assert t1['beatRate'] == 1.0
    
    # Run again: should skip already processed
    mock_urlopen.reset_mock()
    response2 = backtestValidator.handler({}, {})
    assert response2['status'] == 'SUCCESS'
    assert response2['processed'] == 0

@patch('backtestValidator._call_anthropic_api')
@patch('backtestValidator.get_anthropic_key')
def test_run_prompt_auto_tuning(mock_get_key, mock_call_api, setup_aws):
    dynamodb, s3 = setup_aws
    mock_get_key.return_value = 'test-key'
    
    # Mock optimized prompt response from Claude
    mock_call_api.return_value = "```text\n" + ("Optimized prompt text here containing composite_score. " * 20) + "\n```"
    
    # 5 matched pairs to trigger auto-tuning
    matched_pairs = [
        # False Positives
        {
            'score': {'ticker': 'AAPL', 'compositeScore': 8.0, 'oneLineThesis': 'Great'},
            'outcome': {'excessReturnPct': -0.05}
        },
        {
            'score': {'ticker': 'MSFT', 'compositeScore': 8.5, 'oneLineThesis': 'Great'},
            'outcome': {'excessReturnPct': -0.04}
        },
        # False Negatives
        {
            'score': {'ticker': 'TSLA', 'compositeScore': 4.5, 'oneLineThesis': 'Avoid'},
            'outcome': {'excessReturnPct': 0.10}
        },
        {
            'score': {'ticker': 'AMZN', 'compositeScore': 4.0, 'oneLineThesis': 'Avoid'},
            'outcome': {'excessReturnPct': 0.08}
        },
        # Good Prediction
        {
            'score': {'ticker': 'GOOG', 'compositeScore': 7.0, 'oneLineThesis': 'Neutral'},
            'outcome': {'excessReturnPct': 0.03}
        }
    ]
    
    # Case 1: Healthy correlation (>= 0.15) -> Should skip auto-tuning
    backtestValidator.run_prompt_auto_tuning(matched_pairs, 0.25, 'test-bucket')
    mock_call_api.assert_not_called()
    
    # Case 2: Unhealthy correlation (< 0.15) -> Should run auto-tuning and save to S3
    backtestValidator.run_prompt_auto_tuning(matched_pairs, -0.10, 'test-bucket')
    mock_call_api.assert_called_once()
    
    # Verify S3 file was written
    obj = s3.get_object(Bucket='test-bucket', Key='prompts/active_system_prompt.txt')
    saved_prompt = obj['Body'].read().decode('utf-8')
    assert saved_prompt == ("Optimized prompt text here containing composite_score. " * 20).strip()
