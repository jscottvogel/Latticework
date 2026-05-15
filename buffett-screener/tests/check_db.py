import boto3
import json
import os

# Connect to DynamoDB using the credentials in the environment
dynamodb = boto3.client('dynamodb', region_name='us-east-1')

# List tables to find the WeeklyRun table
tables = dynamodb.list_tables()['TableNames']
weekly_run_table = [t for t in tables if 'WeeklyRun' in t]

if not weekly_run_table:
    print("WeeklyRun table not found")
else:
    table_name = weekly_run_table[0]
    print(f"Querying {table_name}...")
    
    response = dynamodb.scan(TableName=table_name)
    items = response.get('Items', [])
    print(f"Found {len(items)} items")
    for item in items:
        # Just print keys to see schema
        print("Item keys:", item.keys())
        if 'createdAt' in item:
            print(f"createdAt: {item['createdAt']}")
        if 'runId' in item:
            print(f"runId: {item['runId']}")
        print("---")
