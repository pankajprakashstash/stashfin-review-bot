"""
config.py — All settings in one place.
Edit ONLY the non-secret values here.
Secrets go in GitHub Secrets, never in this file.
"""
import os

# ── App ───────────────────────────────────────────────
PLAY_PACKAGE_NAME = 'com.stashfin.android'
DAYS_TO_FETCH     = 7       # rolling window — catches delayed reviews too
BATCH_SIZE        = 15      # reviews per Gemini call

# ── Gemini ────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL   = 'gemini-2.5-flash'   # free tier

# ── Gmail ─────────────────────────────────────────────
GMAIL_SENDER       = os.environ.get('GMAIL_SENDER', '')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')

# Team → comma-separated email addresses
# Add or remove teams here. Each team gets a filtered digest.
EMAIL_TEAMS = {
    'Product (All Issues)': {
        'recipients': [e.strip() for e in os.environ.get('EMAIL_PRODUCT', '').split(',') if e.strip()],
        'categories': None,   # None = receives all categories
    },
    'Tech Team': {
        'recipients': [e.strip() for e in os.environ.get('EMAIL_TECH', '').split(',') if e.strip()],
        'categories': ['Technical Issues'],
    },
    'CX / Support': {
        'recipients': [e.strip() for e in os.environ.get('EMAIL_CX', '').split(',') if e.strip()],
        'categories': ['Customer Support', 'KYC / Verification Issues'],
    },
    'Risk & Compliance': {
        'recipients': [e.strip() for e in os.environ.get('EMAIL_RISK', '').split(',') if e.strip()],
        'categories': ['Fraud / Scam', 'Data Privacy / Harassment'],
    },
}
