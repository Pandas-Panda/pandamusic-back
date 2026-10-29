import os
import json
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.environ.get("DATABASE_URL")

# JWT
JWT_SECRET = os.environ.get("JWT_SECRET", "pandamusic_super_secret_jwt_key_2026_oza")
JWT_ACCESS_EXPIRY_HOURS = 24 * 7      # 7 days
JWT_REFRESH_EXPIRY_DAYS = 30

# Magic Link
MAGIC_LINK_EXPIRY_MINUTES = 15
NETLIFY_VERIFY_URL = os.environ.get("NETLIFY_VERIFY_URL", "https://pandamusicforpandas.netlify.app/verify")

# Brevo
BREVO_API_KEY    = os.environ.get("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "pandamusicforpandas@gmail.com")
BREVO_SENDER_NAME  = os.environ.get("BREVO_SENDER_NAME", "PandaMusic")

# Razorpay
RAZORPAY_KEY_ID     = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
SUBSCRIPTION_PRICE_PAISE = 2000   # ₹20 in paise

# Firebase
FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON")

# App
TRIAL_DAYS       = 15
MAX_DEVICES      = 2
MAX_REFERRALS_PER_MONTH = 2
REFERRAL_DISCOUNT_RUPEES = 10
SUBSCRIPTION_PRICE_RUPEES = 20
