import pytest
import json
import os
import decimal
import math
from unittest.mock import MagicMock, patch
from amplify.functions.advisorCompetitionWorker import handler, DecimalEncoder

def test_decimal_encoder():
    encoder = DecimalEncoder()
    assert encoder.encode(decimal.Decimal('10.0')) == '10'
    assert encoder.encode(decimal.Decimal('10.5')) == '10.5'
    assert encoder.encode('abc') == '"abc"'

@patch('boto3.client')
@patch('boto3.resource')
@patch('urllib.request.urlopen')
def test_handler_success(mock_urlopen, mock_resource, mock_client):
    # Mock OS environments
    os.environ['S3_BUCKET'] = 'test-bucket'
    os.environ['DYNAMODB_TABLE_ROLLING_SCORES'] = 'test-rolling-table'
    
    # Mock DynamoDB
    mock_db = MagicMock()
    mock_resource.return_value = mock_db
    mock_table = MagicMock()
    mock_db.Table.return_value = mock_table
    
    # Mock scanning candidates (30 candidates to ensure we meet candidate size requirements)
    candidates = []
    for i in range(1, 35):
        candidates.append({
            'ticker': f'STK{i}',
            'companyName': f'Stock Company {i}',
            'sector': 'Technology',
            'avgCompositeScore': decimal.Decimal('8.5') if i < 15 else decimal.Decimal('5.5'),
            'latestVerdict': 'INVESTIGATE',
            'isInvestable': True,
            'latestThesis': f'Solid cash flows and moat for stock {i}'
        })
        
    mock_table.scan.return_value = {'Items': candidates}
    
    # Mock Secrets Manager for API keys
    mock_sm = MagicMock()
    mock_client.return_value = mock_sm
    mock_sm.get_secret_value.side_effect = [
        {'SecretString': '{"key": "mock-claude-key"}'}, # Anthropic
        {'SecretString': '{"key": "mock-av-key"}'}      # Alpha Vantage
    ]
    
    # Mock Claude responses
    # Return 10 selections for each advisor selection call (3 calls in total: Graham, Munger, Fisher)
    claude_response_data = {
        'selections': [
            {'ticker': f'STK{i}', 'weight': 10} for i in range(1, 11)
        ],
        'thesis': 'Custom simulated advisor thesis selection.'
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        'content': [{'text': json.dumps(claude_response_data)}]
    }).encode('utf-8')
    
    # Mock URL requests
    # URL 1-3: Claude calls. URL 4+: Alpha Vantage fetches.
    # We will mock the returns for URL open. We can use a side effect that yields mock responses based on url or payload.
    # Alpha Vantage returns price data for weekly history.
    av_time_series = {
        'Weekly Adjusted Time Series': {}
    }
    # Populate weekly adjusted time series for 6 months (26 weeks)
    import datetime
    base_date = datetime.date(2026, 1, 2) # Friday
    for week in range(260): # 5 years = 260 weeks
        date_str = (base_date + datetime.timedelta(weeks=week)).strftime('%Y-%m-%d')
        av_time_series['Weekly Adjusted Time Series'][date_str] = {
            '5. adjusted close': str(100.0 + week * 0.5), # gradual growth
            '4. close': str(100.0 + week * 0.5)
        }
        
    def urlopen_side_effect(req, *args, **kwargs):
        # Determine if it's Claude (v1/messages) or Alpha Vantage query
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        resp = MagicMock()
        resp.__enter__.return_value = resp
        if 'api.anthropic.com' in url:
            resp.read.return_value = json.dumps({
                'content': [{'text': json.dumps(claude_response_data)}]
            }).encode('utf-8')
        else:
            # Alpha Vantage mock
            resp.read.return_value = json.dumps(av_time_series).encode('utf-8')
        return resp
        
    mock_urlopen.side_effect = urlopen_side_effect
    
    # Execute Lambda handler
    result = handler({}, None)
    
    # Verify execution output status
    assert result['status'] == 'SUCCESS'
    assert 'Graham' in result['advisors']
    assert 'Munger' in result['advisors']
    assert 'Fisher' in result['advisors']
    assert '6M' in result['horizons_calculated']
    assert '5Y' in result['horizons_calculated']
    
    # Verify S3 upload occurred
    mock_client.return_value.put_object.assert_called_once()
    args, kwargs = mock_client.return_value.put_object.call_args
    assert kwargs['Bucket'] == 'test-bucket'
    assert kwargs['Key'] == 'dashboard/advisor_competition.json'
    
    # Parse uploaded content to verify Recharts compatibility and stats
    uploaded_json = json.loads(kwargs['Body'])
    assert 'updatedAt' in uploaded_json
    assert 'horizons' in uploaded_json
    assert '6M' in uploaded_json['horizons']
    
    # Verify flat timeline format
    timeline = uploaded_json['horizons']['6M']['timeline']
    assert len(timeline) == 26
    assert 'date' in timeline[0]
    assert 'Graham' in timeline[0]
    assert 'Munger' in timeline[0]
    assert 'Fisher' in timeline[0]
    assert 'SPY' in timeline[0]
    
    # Verify stats
    leaderboard = uploaded_json['horizons']['6M']['leaderboard']
    assert len(leaderboard) == 4 # Graham, Munger, Fisher, SPY
    for entity in leaderboard:
        assert 'totalReturn' in entity
        assert 'sharpe' in entity
        assert 'maxDrawdown' in entity
        assert 'alpha' in entity
        assert 'beta' in entity
