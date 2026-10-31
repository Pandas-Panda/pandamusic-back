from flask import Blueprint, request, jsonify, g
from db.connection import get_db_conn
from utils.magic_link_helper import generate_magic_token, send_magic_link, get_expiry
from utils.jwt_helper import generate_access_token, generate_refresh_token, verify_token
from utils.auth_middleware import require_jwt
from utils.referral_helper import generate_referral_code
from config import MAX_DEVICES
import bcrypt

auth_bp = Blueprint('auth', __name__)

# ─── Send Magic Link ─────────────────────────────────────────────────
@auth_bp.route('/auth/send-magic-link', methods=['POST'])
def send_magic_link_route():
    conn = cur = None
    try:
        data          = request.get_json()
        email         = (data.get('email') or '').strip().lower()
        name          = (data.get('name') or '').strip()
        password      = (data.get('password') or '').strip()
        referral_code = (data.get('referral_code') or '').strip().upper()

        if not email:
            return jsonify({'success': False, 'error': 'Email required'}), 400
        if not name:
            return jsonify({'success': False, 'error': 'Name required'}), 400
        if not password or len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        token  = generate_magic_token()
        expiry = get_expiry()

        conn = get_db_conn()
        cur  = conn.cursor()

        cur.execute("UPDATE magic_links SET used = TRUE WHERE email = %s AND used = FALSE", (email,))

        cur.execute(
            """INSERT INTO magic_links (email, token, expires_at, name, password_hash, referral_code_used)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (email, token, expiry, name, password_hash, referral_code or None)
        )
        conn.commit()

        send_magic_link(email, token)
        return jsonify({'success': True, 'message': 'Magic link sent to your email'})

    except Exception as e:
        if conn: conn.rollback()
        print(f"SEND MAGIC LINK ERROR: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

# ─── Verify Magic Link Token ─────────────────────────────────────────
@auth_bp.route('/auth/verify-magic-link', methods=['GET'])
def verify_magic_link():
    conn = cur = None
    try:
        token = request.args.get('token', '').strip()
        if not token:
            return jsonify({'success': False, 'error': 'Token required'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()

        cur.execute(
            "SELECT email, expires_at, used FROM magic_links WHERE token = %s",
            (token,)
        )
        row = cur.fetchone()

        if not row:
            return jsonify({'success': False, 'error': 'Invalid link'}), 400

        email, expires_at, used = row

        if used:
            return jsonify({'success': False, 'error': 'Link already used'}), 400

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            from datetime import timezone
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now > expires_at:
            return jsonify({'success': False, 'error': 'Link expired'}), 400

        # Mark link as used
        cur.execute("UPDATE magic_links SET used = TRUE WHERE token = %s", (token,))

        # Get or create user
        cur.execute("SELECT id, name, referral_code FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        is_new_user = False

        if not user:
            is_new_user   = True
            # Pull name, password_hash, referral_code_used from the magic_link row
            cur.execute(
                "SELECT name, password_hash, referral_code_used FROM magic_links WHERE token = %s",
                (token,)
            )
            link_meta = cur.fetchone()
            reg_name          = link_meta[0] if link_meta else None
            reg_password_hash = link_meta[1] if link_meta else None
            reg_referral_used = link_meta[2] if link_meta else None

            new_referral_code = generate_referral_code()
            cur.execute(
                """INSERT INTO users (email, name, password_hash, referral_code, referred_by)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id, name, referral_code""",
                (email, reg_name, reg_password_hash, new_referral_code, reg_referral_used)
            )
            user = cur.fetchone()

                # Mark email as verified
        cur.execute("UPDATE users SET email_verified = TRUE WHERE email = %s", (email,))
        conn.commit()

        # Redirect to app login screen via deep link
        return jsonify({
            'success': True,
            'deep_link': f"pandamusic://verified?email={email}"
        })

    except Exception as e:
        if conn: conn.rollback()
        print(f"VERIFY MAGIC LINK ERROR: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Refresh Token ────────────────────────────────────────────────────
@auth_bp.route('/auth/refresh-token', methods=['POST'])
def refresh_token():
    conn = cur = None
    try:
        data          = request.get_json()
        refresh_tok   = (data.get('refresh_token') or '').strip()
        payload       = verify_token(refresh_tok, token_type='refresh')

        if not payload:
            return jsonify({'success': False, 'error': 'Invalid or expired refresh token'}), 401

        user_id = payload['user_id']

        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        email        = row[0]
        access_token = generate_access_token(user_id, email)
        return jsonify({'success': True, 'token': access_token})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Register Device ─────────────────────────────────────────────────
@auth_bp.route('/auth/register-device', methods=['POST'])
@require_jwt
def register_device():
    conn = cur = None
    try:
        data        = request.get_json()
        device_id   = (data.get('device_id') or '').strip()
        device_name = (data.get('device_name') or 'Unknown Device').strip()
        user_id     = g.user_id

        if not device_id:
            return jsonify({'success': False, 'error': 'device_id required'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()

        # Check if this device is already registered to this user
        cur.execute(
            "SELECT id FROM devices WHERE device_id = %s AND user_id = %s",
            (device_id, user_id)
        )
        if cur.fetchone():
            # Already registered — just update last_seen
            cur.execute(
                "UPDATE devices SET last_seen = NOW() WHERE device_id = %s",
                (device_id,)
            )
            conn.commit()
            return jsonify({'success': True, 'message': 'Device already registered'})

        # Count active devices for this user
        cur.execute("SELECT COUNT(*) FROM devices WHERE user_id = %s", (user_id,))
        count = cur.fetchone()[0]

        if count >= MAX_DEVICES:
            # Return list of registered devices so user can remove one
            cur.execute(
                "SELECT device_id, device_name, last_seen FROM devices WHERE user_id = %s ORDER BY last_seen DESC",
                (user_id,)
            )
            devices = [
                {'device_id': r[0], 'device_name': r[1], 'last_seen': r[2].isoformat()}
                for r in cur.fetchall()
            ]
            return jsonify({'success': False, 'error': 'Device limit reached', 'devices': devices}), 403

        cur.execute(
            "INSERT INTO devices (user_id, device_id, device_name) VALUES (%s, %s, %s)",
            (user_id, device_id, device_name)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Device registered'})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Remove Device ───────────────────────────────────────────────────
@auth_bp.route('/auth/remove-device', methods=['DELETE'])
@require_jwt
def remove_device():
    conn = cur = None
    try:
        data      = request.get_json()
        device_id = (data.get('device_id') or '').strip()
        user_id   = g.user_id

        if not device_id:
            return jsonify({'success': False, 'error': 'device_id required'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            "DELETE FROM devices WHERE device_id = %s AND user_id = %s",
            (device_id, user_id)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Device removed'})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── List Devices ────────────────────────────────────────────────────
@auth_bp.route('/auth/devices', methods=['GET'])
@require_jwt
def list_devices():
    conn = cur = None
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT device_id, device_name, last_seen FROM devices WHERE user_id = %s ORDER BY last_seen DESC",
            (g.user_id,)
        )
        devices = [
            {'device_id': r[0], 'device_name': r[1], 'last_seen': r[2].isoformat()}
            for r in cur.fetchall()
        ]
        return jsonify({'success': True, 'devices': devices})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

# ─── Login (email + password) ────────────────────────────────────────
@auth_bp.route('/auth/login', methods=['POST'])
def login():
    conn = cur = None
    try:
        data     = request.get_json()
        email    = (data.get('email') or '').strip().lower()
        password = (data.get('password') or '').strip()

        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password required'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()

        cur.execute(
            "SELECT id, name, referral_code, password_hash, email_verified FROM users WHERE email = %s",
            (email,)
        )
        user = cur.fetchone()

        if not user:
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401

        user_id, name, referral_code, password_hash, email_verified = user

        if not email_verified:
            return jsonify({'success': False, 'error': 'Please verify your email first'}), 403

        if not password_hash or not bcrypt.checkpw(password.encode(), password_hash.encode()):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401

        access_token  = generate_access_token(user_id, email)
        refresh_token = generate_refresh_token(user_id)

        return jsonify({
            'success':       True,
            'token':         access_token,
            'refresh_token': refresh_token,
            'user': {
                'id':            user_id,
                'email':         email,
                'name':          name,
                'referral_code': referral_code
            }
        })

    except Exception as e:
        print(f"LOGIN ERROR: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()