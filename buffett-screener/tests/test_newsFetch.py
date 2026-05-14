import os
import json
import pytest
from unittest.mock import patch, MagicMock
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../amplify/functions')))
import newsFetch

@patch('newsFetch.get_newsapi_key')
@patch('urllib.request.urlopen')
def test_handler(mock_urlopen, mock_get_key):
    mock_get_key.return_value = 'TEST_KEY'
    
    def urlopen_side_effect(req, *args, **kwargs):
        url = req.full_url if hasattr(req, 'full_url') else req
        mock_resp = MagicMock()
        
        if 'newsapi.org' in url:
            mock_resp.read.return_value = json.dumps({
                'articles': [
                    {'title': 'Apple makes a new thing', 'description': 'It is very cool.', 'publishedAt': '2026-05-14', 'source': {'name': 'TechCrunch'}},
                    {'title': 'Apple makes a new thing', 'description': 'Duplicate article.', 'publishedAt': '2026-05-14', 'source': {'name': 'Other'}}
                ]
            }).encode('utf-8')
        elif 'finance.yahoo.com' in url or 'news.google.com' in url:
            xml = """<?xml version="1.0"?>
            <rss version="2.0">
                <channel>
                    <item>
                        <title>Apple stock up</title>
                        <description>It went up.</description>
                        <pubDate>Thu, 14 May 2026 12:00:00 GMT</pubDate>
                    </item>
                </channel>
            </rss>"""
            mock_resp.read.return_value = xml.encode('utf-8')
        else:
            mock_resp.read.return_value = b''
            
        return MagicMock(__enter__=MagicMock(return_value=mock_resp))
        
    mock_urlopen.side_effect = urlopen_side_effect
    
    event = {
        'run_id': '2026-W01',
        'candidates': [
            {'ticker': 'AAPL', 'name': 'Apple'}
        ]
    }
    
    response = newsFetch.handler(event, {})
    
    assert 'news' in response
    news_dict = response['news']
    assert 'AAPL' in news_dict
    summary = news_dict['AAPL']
    
    # Should contain deduplicated articles
    assert "Apple makes a new thing" in summary
    assert "Apple stock up" in summary
    assert summary.count("Apple makes a new thing") == 1 # Deduplicated
