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
DAYS_TO_FETCH        = 7
MAX_REVIEWS_PER_STAR = 850
# ── Gemini ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL   = 'gemini-flash-latest'
BATCH_SIZE     = 35
# ── Gmail ──────────────────────────────────────────────────────────
GMAIL_SENDER       = os.environ.get('GMAIL_SENDER', '')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')
EMAIL_ALL = [
    e.strip()
    for e in os.environ.get('EMAIL_ALL', '').split(',')
    if e.strip()
]
# ── GitHub Pages ───────────────────────────────────────────────────
PAGES_URL = 'https://vishalvijayvergiya.github.io/stashfin-review-bot/'
# ── History ────────────────────────────────────────────────────────
MAX_HISTORY_WEEKS = 8
TABLE_WEEKS       = 4
# ── StashFin brand colors ──────────────────────────────────────────
BRAND_CORAL    = '#FF4040'
BRAND_BLUE     = '#1B3A6B'
BRAND_CORAL_LT = '#FFF0F0'
BRAND_BLUE_LT  = '#EEF2F9'
# Issue colors — strictly StashFin red and blue shades only
# Alternates between coral red and brand blue variants
ISSUE_COLORS = [
    '#FF4040',   # StashFin coral red        (rank 1)
    '#1B3A6B',   # StashFin brand blue       (rank 2)
    '#CC2020',   # Darker red                (rank 3)
    '#2C5F9E',   # Medium blue               (rank 4)
    '#FF7070',   # Lighter red               (rank 5)
    '#4A7BC5',   # Lighter blue              (rank 6)
    '#991515',   # Deep red                  (rank 7+)
    '#0F2548',   # Deep navy                 (rank 8+)
]
