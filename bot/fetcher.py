"""
fetcher.py
Fetches 1-2-3 star reviews from Play Store using google-play-scraper.
Only pulls reviews from the last DAYS_TO_FETCH days.
Automatically skips reviews with no text (nothing to classify).
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from google_play_scraper import reviews, Sort
from bot.config import PLAY_PACKAGE_NAME, DAYS_TO_FETCH

log = logging.getLogger(__name__)


def fetch_reviews() -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_FETCH)
    log.info(f'Fetching 1-2-3★ reviews for {PLAY_PACKAGE_NAME} since {cutoff.date()}...')

    result, _ = reviews(
        PLAY_PACKAGE_NAME,
        lang='en',
        country='in',
        sort=Sort.NEWEST,
        count=800,          # fetch more than needed, we filter below
        filter_score_with=None,
    )

    filtered = []
    for r in result:
        rating = int(r.get('score', 0))
        if rating > 3:
            continue        # skip 4 and 5 star — no wasted Gemini calls

        dt = r.get('at')
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                break       # sorted newest first — once we go past cutoff, stop

        text = (r.get('content') or '').strip()

        filtered.append({
            'review_id': r.get('reviewId', ''),
            'text':      text,
            'rating':    rating,
            'date':      dt.strftime('%Y-%m-%d') if dt else '',
            'has_text':  bool(text),
        })

    log.info(f'Fetched {len(filtered)} reviews (1-2-3★, last {DAYS_TO_FETCH} days)')
    return filtered
