import jwt
import datetime
from config import JWT_SECRET, JWT_ACCESS_EXPIRY_HOURS, JWT_REFRESH_EXPIRY_DAYS

def generate_access_token(user_id, email):
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_ACCESS_EXPIRY_HOURS),
        'type': 'access'
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def generate_refresh_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=JWT_REFRESH_EXPIRY_DAYS),
        'type': 'refresh'
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_token(token, token_type='access'):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        if payload.get('type') != token_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
