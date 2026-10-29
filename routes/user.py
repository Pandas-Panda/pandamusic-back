from flask import Blueprint, request, jsonify, g
from db.connection import get_db_conn
from utils.auth_middleware import require_jwt
from config import MAX_REFERRALS_PER_MONTH, REFERRAL_DISCOUNT_RUPEES
from datetime import datetime

user_bp = Blueprint('user', __name__)


# ─── Get Profile ─────────────────────────────────────────────────────
@user_bp.route('/user/profile', methods=['GET'])
@require_jwt
def get_profile():
    conn = cur = None
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            SELECT name, email, referral_code, subscription_active,
                   subscription_expiry, trial_start_date
            FROM users WHERE id = %s
            """,
            (g.user_id,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        name, email, referral_code, sub_active, sub_expiry, trial_start = row

        from config import TRIAL_DAYS
        trial_days_remaining = 0
        if trial_start:
            elapsed = (datetime.utcnow() - trial_start.replace(tzinfo=None)).days
            trial_days_remaining = max(0, TRIAL_DAYS - elapsed)

        return jsonify({
            'success': True,
            'name':                 name,
            'email':                email,
            'referral_code':        referral_code,
            'subscription_active':  sub_active,
            'subscription_expiry':  sub_expiry.isoformat() if sub_expiry else None,
            'trial_days_remaining': trial_days_remaining
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Update Profile ───────────────────────────────────────────────────
@user_bp.route('/user/profile', methods=['PUT'])
@require_jwt
def update_profile():
    conn = cur = None
    try:
        data = request.get_json()
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name required'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("UPDATE users SET name = %s WHERE id = %s", (name, g.user_id))
        conn.commit()
        return jsonify({'success': True})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Get Referral Info ────────────────────────────────────────────────
@user_bp.route('/user/referral/code', methods=['GET'])
@require_jwt
def get_referral_code():
    conn = cur = None
    try:
        month = datetime.utcnow().strftime('%Y-%m')
        conn  = get_db_conn()
        cur   = conn.cursor()

        cur.execute("SELECT referral_code FROM users WHERE id = %s", (g.user_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        referral_code = row[0]

        # Count how many people used this code this month
        cur.execute(
            """
            SELECT COUNT(*) FROM referral_discounts
            WHERE user_id = %s AND source = 'referral' AND month = %s
            """,
            (g.user_id, month)
        )
        uses_this_month = cur.fetchone()[0]

        discount_earned = min(uses_this_month, MAX_REFERRALS_PER_MONTH) * REFERRAL_DISCOUNT_RUPEES

        return jsonify({
            'success':              True,
            'referral_code':        referral_code,
            'uses_this_month':      uses_this_month,
            'discount_earned_this_month': discount_earned
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Apply Referral Code ──────────────────────────────────────────────
@user_bp.route('/user/referral/apply', methods=['POST'])
@require_jwt
def apply_referral():
    conn = cur = None
    try:
        data          = request.get_json()
        referral_code = (data.get('referral_code') or '').strip().upper()
        month         = datetime.utcnow().strftime('%Y-%m')

        if not referral_code:
            return jsonify({'success': False, 'error': 'referral_code required'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()

        # Find referrer
        cur.execute("SELECT id FROM users WHERE referral_code = %s", (referral_code,))
        referrer = cur.fetchone()
        if not referrer:
            return jsonify({'success': False, 'error': 'Invalid referral code'}), 400

        referrer_id = referrer[0]

        if referrer_id == g.user_id:
            return jsonify({'success': False, 'error': 'Cannot use your own referral code'}), 400

        # Check if current user already applied a referral code
        cur.execute("SELECT referred_by FROM users WHERE id = %s", (g.user_id,))
        already = cur.fetchone()
        if already and already[0]:
            return jsonify({'success': False, 'error': 'You already used a referral code'}), 400

        # Check referrer hasn't exceeded max referrals this month
        cur.execute(
            "SELECT COUNT(*) FROM referral_discounts WHERE user_id = %s AND source = 'referral' AND month = %s",
            (referrer_id, month)
        )
        referrer_uses = cur.fetchone()[0]
        if referrer_uses >= MAX_REFERRALS_PER_MONTH:
            return jsonify({'success': False, 'error': 'Referrer has reached max referrals this month'}), 400

        # Apply ₹10 discount to referrer
        cur.execute(
            "INSERT INTO referral_discounts (user_id, source, amount, month) VALUES (%s, 'referral', %s, %s)",
            (referrer_id, REFERRAL_DISCOUNT_RUPEES, month)
        )

        # Apply ₹10 discount to new user (first paid month)
        cur.execute(
            "INSERT INTO referral_discounts (user_id, source, amount, month) VALUES (%s, 'referral', %s, %s)",
            (g.user_id, REFERRAL_DISCOUNT_RUPEES, month)
        )

        # Store referred_by on user
        cur.execute("UPDATE users SET referred_by = %s WHERE id = %s", (referral_code, g.user_id))
        conn.commit()

        return jsonify({'success': True, 'discount_applied': REFERRAL_DISCOUNT_RUPEES})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Register FCM Token ───────────────────────────────────────────────
@user_bp.route('/notifications/register', methods=['POST'])
@require_jwt
def register_fcm():
    conn = cur = None
    try:
        data      = request.get_json()
        fcm_token = (data.get('fcm_token') or '').strip()
        if not fcm_token:
            return jsonify({'success': False, 'error': 'fcm_token required'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute("UPDATE users SET fcm_token = %s WHERE id = %s", (fcm_token, g.user_id))
        conn.commit()
        return jsonify({'success': True})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()
