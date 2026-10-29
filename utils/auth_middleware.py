from functools import wraps
from flask import request, jsonify, g
from utils.jwt_helper import verify_token

def require_jwt(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Missing token'}), 401

        token = auth_header.split(' ', 1)[1]
        payload = verify_token(token, token_type='access')

        if not payload:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401

        # Make user_id and email available to the route via flask.g
        g.user_id = payload['user_id']
        g.email   = payload['email']
        return f(*args, **kwargs)

    return decorated
