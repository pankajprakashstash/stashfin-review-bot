"""
config.py — All settings in one place.
Secrets go in GitHub Secrets only — never in this file.

FIRST TWO TEST RUNS:
  Run 1: Keep DAYS_TO_FETCH = 14  → builds baseline history
  Run 2: Change to DAYS_TO_FETCH = 7 → first real comparison email
  Week 3 onwards: stays at 7 forever
"""
import os

# ── App ────────────────────────────────────────────────────────────
PLAY_PACKAGE_NAME    = 'com.stashfin.android'
DAYS_TO_FETCH        = 7     # ← CHANGE TO 7 AFTER FIRST TEST RUN
MAX_REVIEWS_PER_STAR = 850    # 850 × 3 stars = 2550 capacity

# ── Gemini ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL   = 'gemini-2.5-flash'    # 1500 req/day free
BATCH_SIZE     = 30

# ── Gmail ──────────────────────────────────────────────────────────
GMAIL_SENDER       = os.environ.get('GMAIL_SENDER', '')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')
EMAIL_ALL = [
    e.strip()
    for e in os.environ.get('EMAIL_ALL', '').split(',')
    if e.strip()
]

# ── GitHub Pages detail page URL ───────────────────────────────────
PAGES_URL = 'https://vishalvijayvergiya.github.io/stashfin-review-bot/'

# ── History ────────────────────────────────────────────────────────
MAX_HISTORY_WEEKS  = 8    # weeks stored in history.json
TABLE_WEEKS        = 4    # weeks shown in the comparison table

# ── Brand colors ───────────────────────────────────────────────────
BRAND_CORAL    = '#FF4040'
BRAND_BLUE     = '#1B3A6B'
BRAND_CORAL_LT = '#FFF5F5'
BRAND_BLUE_LT  = '#EEF2F9'

# Issue color palette — assigned by rank (top issue = color 0, etc.)
ISSUE_COLORS = [
    '#FF4040',   # rank 1 — coral red
    '#1B3A6B',   # rank 2 — brand blue
    '#E07800',   # rank 3 — orange
    '#6B35A0',   # rank 4 — purple
    '#0077B6',   # rank 5 — teal
    '#C0392B',   # rank 6 — dark red
    '#2C6E49',   # rank 7 — forest green
    '#555555',   # rank 8+ — gray
]
