"""
config.py — All settings in one place.
Edit ONLY the non-secret values here.
Secrets go in GitHub Secrets, never in this file.
"""
import os

# ── App ───────────────────────────────────────────────
PLAY_PACKAGE_NAME = 'com.stashfin.android'
DAYS_TO_FETCH     = 7
BATCH_SIZE        = 15

# ── Gemini ────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL   = 'gemini-2.5-flash'

# ── Gmail ─────────────────────────────────────────────
GMAIL_SENDER       = os.environ.get('GMAIL_SENDER', '')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')

# Single email goes to everyone — add addresses to EMAIL_ALL in GitHub Secrets
# Format: comma-separated  e.g. "vishal@stashfin.com,gautam@stashfin.com,cto@stashfin.com"
EMAIL_ALL = [
    e.strip()
    for e in os.environ.get('EMAIL_ALL', '').split(',')
    if e.strip()
]
