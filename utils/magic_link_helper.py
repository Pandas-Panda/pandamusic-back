import secrets
import datetime
import requests
from config import (
    BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME,
    NETLIFY_VERIFY_URL, MAGIC_LINK_EXPIRY_MINUTES
)

def generate_magic_token():
    return secrets.token_urlsafe(32)

def send_magic_link(email, token):
    magic_url = f"{NETLIFY_VERIFY_URL}?token={token}"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; background: #0A0A0A; color: #ffffff; padding: 32px; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 24px;">
            <h1 style="color: #E24B4A; font-size: 28px; margin: 0;">🐼 PandaMusic</h1>
        </div>
        <h2 style="font-size: 20px; margin-bottom: 8px;">Sign in to PandaMusic</h2>
        <p style="color: #888888; margin-bottom: 24px;">
            Click the button below to sign in. This link expires in {MAGIC_LINK_EXPIRY_MINUTES} minutes.
        </p>
        <div style="text-align: center; margin-bottom: 24px;">
            <a href="{magic_url}"
               style="background: #E24B4A; color: #ffffff; padding: 14px 32px;
                      border-radius: 8px; text-decoration: none; font-size: 16px;
                      font-weight: bold; display: inline-block;">
                Sign In to PandaMusic
            </a>
        </div>
        <p style="color: #555555; font-size: 13px; text-align: center;">
            If you didn't request this, just ignore this email.
        </p>
    </div>
    """

    payload = {
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to": [{"email": email}],
        "subject": "🐼 Sign in to PandaMusic",
        "htmlContent": html_content
    }

    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        json=payload,
        headers=headers
    )

    if response.status_code not in (200, 201):
        raise Exception(f"Brevo error: {response.text}")

    return True

def get_expiry():
    return datetime.datetime.utcnow() + datetime.timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)
