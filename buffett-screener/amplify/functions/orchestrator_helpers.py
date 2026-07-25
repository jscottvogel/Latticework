import json
import os
import boto3
from botocore.config import Config
import time
from datetime import datetime, timezone, timedelta

_TRIGGER_SECRET = None

def get_trigger_secret(secret_name='/buffett-screener/trigger-secret'):
    global _TRIGGER_SECRET
    if _TRIGGER_SECRET:
        return _TRIGGER_SECRET
    client = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret_string = response.get('SecretString', '').strip()
        if not secret_string:
            return None
        try:
            secret_dict = json.loads(secret_string)
            if isinstance(secret_dict, dict):
                _TRIGGER_SECRET = secret_dict.get('key') or secret_dict.get('secret') or secret_dict.get('apiKey') or secret_dict.get('trigger-secret') or secret_dict.get('value')
                if not _TRIGGER_SECRET and secret_dict:
                    _TRIGGER_SECRET = next(iter(secret_dict.values()))
            else:
                _TRIGGER_SECRET = str(secret_dict)
        except (json.JSONDecodeError, TypeError):
            import re
            match = re.search(r'[\'"]?(?:key|secret|value)[\'"]?\s*[:=]\s*[\'"]?([A-Za-z0-9\-]+)[\'"]?', secret_string)
            if match:
                _TRIGGER_SECRET = match.group(1)
            else:
                _TRIGGER_SECRET = secret_string.strip('\'"{} ')
        return _TRIGGER_SECRET
    except Exception as e:
        print(f"Error fetching trigger secret: {e}")
        return None

def get_run_id():
    now = datetime.now(timezone.utc)
    day_of_year = now.timetuple().tm_yday
    return f'{now.year}-D{day_of_year:03d}'

def is_us_holiday_or_weekend(dt):
    # 0 = Monday, 6 = Sunday
    if dt.weekday() in (5, 6):
        return True
        
    year = dt.year
    month = dt.month
    day = dt.day

    def get_nth_weekday(year, month, weekday, n):
        if n > 0:
            count = 0
            for d in range(1, 32):
                try:
                    curr = datetime(year, month, d)
                    if curr.weekday() == weekday:
                        count += 1
                        if count == n:
                            return d
                except ValueError:
                    break
        else:
            for d in range(31, 0, -1):
                try:
                    curr = datetime(year, month, d)
                    if curr.weekday() == weekday:
                        return d
                except ValueError:
                    pass
        return None

    holidays = set()
    
    # New Year's Day
    jan1 = datetime(year, 1, 1)
    if jan1.weekday() == 6:
        holidays.add((year, 1, 2))
    else:
        holidays.add((year, 1, 1))
        
    # MLK Day: 3rd Monday in Jan
    holidays.add((year, 1, get_nth_weekday(year, 1, 0, 3)))
    
    # Presidents' Day: 3rd Monday in Feb
    holidays.add((year, 2, get_nth_weekday(year, 2, 0, 3)))
    
    # Good Friday
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month_easter = (h + l - 7 * m + 114) // 31
    day_easter = ((h + l - 7 * m + 114) % 31) + 1
    easter = datetime(year, month_easter, day_easter)
    good_friday = easter - timedelta(days=2)
    holidays.add((year, good_friday.month, good_friday.day))
    
    # Memorial Day: last Monday in May
    holidays.add((year, 5, get_nth_weekday(year, 5, 0, -1)))
    
    # Juneteenth: June 19
    j19 = datetime(year, 6, 19)
    if j19.weekday() == 5:
        holidays.add((year, 6, 18))
    elif j19.weekday() == 6:
        holidays.add((year, 6, 20))
    else:
        holidays.add((year, 6, 19))
        
    # Independence Day: July 4
    jul4 = datetime(year, 7, 4)
    if jul4.weekday() == 5:
        holidays.add((year, 7, 3))
    elif jul4.weekday() == 6:
        holidays.add((year, 7, 5))
    else:
        holidays.add((year, 7, 4))
        
    # Labor Day: 1st Monday in Sep
    holidays.add((year, 9, get_nth_weekday(year, 9, 0, 1)))
    
    # Thanksgiving: 4th Thursday in Nov
    holidays.add((year, 11, get_nth_weekday(year, 11, 3, 4)))
    
    # Christmas: Dec 25
    dec25 = datetime(year, 12, 25)
    if dec25.weekday() == 5:
        holidays.add((year, 12, 24))
    elif dec25.weekday() == 6:
        holidays.add((year, 12, 26))
    else:
        holidays.add((year, 12, 25))
        
    return (year, month, day) in holidays

def invoke_lambda(function_name_env_key, payload):
    function_arn = os.environ.get(function_name_env_key)
    if not function_arn:
        raise RuntimeError(f"Missing environment variable: {function_name_env_key}")
        
    config = Config(read_timeout=900, connect_timeout=60, retries={'max_attempts': 0})
    client = boto3.client('lambda', config=config)
    print(f"Invoking {function_arn} synchronously...")
    start_t = time.time()
    
    response = client.invoke(
        FunctionName=function_arn,
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )
    
    elapsed = time.time() - start_t
    print(f"Invocation completed in {elapsed:.1f}s")
    
    if 'FunctionError' in response:
        error_msg = response['Payload'].read().decode('utf-8')
        raise RuntimeError(f"Lambda {function_arn} failed: {error_msg}")
        
    return json.loads(response['Payload'].read().decode('utf-8'))

def send_alert(subject, message):
    sns_arn = os.environ.get('SNS_ALERT_ARN')
    if sns_arn:
        sns = boto3.client('sns')
        try:
            sns.publish(
                TopicArn=sns_arn,
                Subject=subject,
                Message=message
            )
            print("Alert sent via SNS.")
        except Exception as e:
            print(f"Failed to send SNS alert: {e}")
