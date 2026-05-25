import urllib.request
import json

url = "https://dggugtdqmbcilk5mk43axb2ixy.appsync-api.us-east-1.amazonaws.com/graphql"
headers = {
    "x-api-key": "da2-vgyu7lqg2vcbbm2w5etpxf2psy",
    "Content-Type": "application/json"
}

# GraphQL queries
runs_query = """
query ListWeeklyRuns {
  listWeeklyRuns(limit: 1000) {
    items {
      runId
      runDate
      status
      createdAt
    }
  }
}
"""

def make_query(query_str):
    req = urllib.request.Request(
        url, 
        data=json.dumps({"query": query_str}).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error querying AppSync: {e}")
        return None

res = make_query(runs_query)
if res:
    items = res.get('data', {}).get('listWeeklyRuns', {}).get('items', [])
    print(f"Total runs found: {len(items)}")
    
    # Sort runs by createdAt descending
    items.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
    
    for r in items[:10]:
        run_id = r['runId']
        run_date = r.get('runDate')
        status = r.get('status')
        created_at = r.get('createdAt')
        
        # Query count of scores for this run
        scores_query = f"""
        query ListStockScores {{
          listStockScores(filter: {{ runId: {{ eq: "{run_id}" }} }}, limit: 1000) {{
            items {{
              ticker
              compositeScore
              verdict
            }}
          }}
        }}
        """
        scores_res = make_query(scores_query)
        score_items = scores_res.get('data', {}).get('listStockScores', {}).get('items', []) if scores_res else []
        print(f"Run: {run_id} | Date: {run_date} | Status: {status} | CreatedAt: {created_at} | Scores count: {len(score_items)}")
        if score_items:
            # Print top 3 scores
            sorted_scores = sorted(score_items, key=lambda x: x.get('compositeScore') or 0, reverse=True)
            top_3 = [f"{s['ticker']}:{s.get('compositeScore')}" for s in sorted_scores[:3]]
            print(f"  Top scores: {', '.join(top_3)}")
else:
    print("Failed to fetch runs.")
