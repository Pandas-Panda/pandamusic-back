import razorpay
import hmac
import hashlib
from flask import Blueprint, request, jsonify, g
from db.connection import get_db_conn
from utils.auth_middleware import require_jwt
from config import (
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
    SUBSCRIPTION_PRICE_PAISE, SUBSCRIPTION_PRICE_RUPEES,
    TRIAL_DAYS
)
from datetime import datetime, timedelta

subscription_bp = Blueprint('subscription', __name__)

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def get_discount_for_user(cur, user_id, month):
    """Returns total discount in rupees for user this month (capped at ₹20)."""
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM referral_discounts WHERE user_id = %s AND month = %s AND applied = FALSE",
        (user_id, month)
    )
    total = cur.fetchone()[0]
    return min(int(total), SUBSCRIPTION_PRICE_RUPEES)


# ─── Subscription Status ──────────────────────────────────────────────
@subscription_bp.route('/subscription/status', methods=['GET'])
@require_jwt
def subscription_status():
    conn = cur = None
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT subscription_active, subscription_expiry, trial_start_date FROM users WHERE id = %s",
            (g.user_id,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        sub_active, sub_expiry, trial_start = row
        now = datetime.utcnow()

        # Trial check
        trial_days_remaining = 0
        if trial_start:
            elapsed = (now - trial_start.replace(tzinfo=None)).days
            trial_days_remaining = max(0, TRIAL_DAYS - elapsed)

        # Subscription check
        is_subscribed = (
            sub_active and sub_expiry and sub_expiry.replace(tzinfo=None) > now
        )

        month    = now.strftime('%Y-%m')
        discount = get_discount_for_user(cur, g.user_id, month)

        return jsonify({
            'success':              True,
            'active':               bool(trial_days_remaining > 0 or is_subscribed),
            'trial_days_remaining': trial_days_remaining,
            'is_subscribed':        is_subscribed,
            'expiry_date':          sub_expiry.isoformat() if sub_expiry else None,
            'discount_this_month':  discount
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Create Razorpay Order ────────────────────────────────────────────
@subscription_bp.route('/subscription/create-order', methods=['POST'])
@require_jwt
def create_order():
    conn = cur = None
    try:
        now   = datetime.utcnow()
        month = now.strftime('%Y-%m')

        conn = get_db_conn()
        cur  = conn.cursor()

        discount       = get_discount_for_user(cur, g.user_id, month)
        final_rupees   = max(0, SUBSCRIPTION_PRICE_RUPEES - discount)
        final_paise    = final_rupees * 100

        if final_paise == 0:
            # Free month — activate directly without Razorpay
            expiry = now + timedelta(days=30)
            cur.execute(
                "UPDATE users SET subscription_active = TRUE, subscription_expiry = %s WHERE id = %s",
                (expiry, g.user_id)
            )
            # Mark discounts as applied
            cur.execute(
                "UPDATE referral_discounts SET applied = TRUE WHERE user_id = %s AND month = %s AND applied = FALSE",
                (g.user_id, month)
            )
            conn.commit()
            return jsonify({
                'success':      True,
                'free_month':   True,
                'expiry_date':  expiry.isoformat()
            })

        # Create Razorpay order
        order = razorpay_client.order.create({
            'amount':   final_paise,
            'currency': 'INR',
            'notes':    {'user_id': str(g.user_id), 'month': month}
        })

        cur.execute(
            "INSERT INTO payment_orders (user_id, razorpay_order_id, amount_paise) VALUES (%s, %s, %s)",
            (g.user_id, order['id'], final_paise)
        )
        conn.commit()

        return jsonify({
            'success':         True,
            'free_month':      False,
            'order_id':        order['id'],
            'amount_paise':    final_paise,
            'amount_rupees':   final_rupees,
            'discount_rupees': discount,
            'key_id':          RAZORPAY_KEY_ID
        })

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Verify Payment & Activate ────────────────────────────────────────
@subscription_bp.route('/subscription/verify-payment', methods=['POST'])
@require_jwt
def verify_payment():
    conn = cur = None
    try:
        data               = request.get_json()
        razorpay_order_id  = data.get('razorpay_order_id', '')
        razorpay_payment_id = data.get('razorpay_payment_id', '')
        razorpay_signature = data.get('razorpay_signature', '')

        # Verify signature
        body = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_sig = hmac.new(
            RAZORPAY_KEY_SECRET.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        if expected_sig != razorpay_signature:
            return jsonify({'success': False, 'error': 'Invalid payment signature'}), 400

        now   = datetime.utcnow()
        month = now.strftime('%Y-%m')

        conn = get_db_conn()
        cur  = conn.cursor()

        # Mark order as paid
        cur.execute(
            "UPDATE payment_orders SET status = 'paid' WHERE razorpay_order_id = %s AND user_id = %s",
            (razorpay_order_id, g.user_id)
        )

        # Activate subscription
        expiry = now + timedelta(days=30)
        cur.execute(
            "UPDATE users SET subscription_active = TRUE, subscription_expiry = %s WHERE id = %s",
            (expiry, g.user_id)
        )

        # Mark discounts as applied
        cur.execute(
            "UPDATE referral_discounts SET applied = TRUE WHERE user_id = %s AND month = %s AND applied = FALSE",
            (g.user_id, month)
        )
        conn.commit()

        return jsonify({
            'success':     True,
            'expiry_date': expiry.isoformat()
        })

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()
