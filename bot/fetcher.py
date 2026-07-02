"""
fetcher.py
==========
Fetches 1-2-3★ reviews from Play Store using google-play-scraper.

Key approach:
- Fetches each star rating (1, 2, 3) separately using filter_score_with
  so the count limit is never wasted on 4-5 star reviews
- Fetches across multiple languages to catch Hindi, Hinglish, and
  regional language reviews that a single en/in call would miss
- Deduplicates by review ID so no review is counted twice
- Only returns reviews within the last DAYS_TO_FETCH days
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from google_play_scraper import reviews, Sort
from bot.config import PLAY_PACKAGE_NAME, DAYS_TO_FETCH

log = logging.getLogger(__name__)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def fetch_reviews() -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_FETCH)

    # Languages to fetch — covers English, Hindi, and falls back to
    # no-language-filter (None) which returns whatever Play Store
    # serves by default for India, catching Hinglish and regional mix
    LANGUAGES = ['en', 'hi', None]

    # Each star rating fetched separately so count limit is not
    # wasted on 4-5 star reviews
    STAR_RATINGS = [1, 2, 3]

    # 500 per call per star per language — at StashFin's current
    # weekly volume (~90-100 negative reviews/week) this is more
    # than enough headroom. Increase to 1000 if volume grows.
    COUNT_PER_CALL = 500

    seen_ids: set     = set()
    all_reviews: list = []
    total_calls       = 0
    total_fetched     = 0

    for star in STAR_RATINGS:
        for lang in LANGUAGES:
            lang_label = lang if lang else 'default'
            try:
                result, _ = reviews(
                    PLAY_PACKAGE_NAME,
                    lang              = lang,
                    country           = 'in',
                    sort              = Sort.NEWEST,
                    count             = COUNT_PER_CALL,
                    filter_score_with = star,
                )
                total_calls   += 1
                total_fetched += len(result)

                for r in result:
                    rid = r.get('reviewId', '')

                    # Skip if already seen from another language call
                    if not rid or rid in seen_ids:
                        continue
                    seen_ids.add(rid)

                    # Date check — skip reviews outside our window
                    dt = r.get('at')
                    if dt:
                        dt = _to_utc(dt)
                        if dt < cutoff:
                            continue   # older than our window, skip
                    else:
                        continue       # no date at all, skip

                    text = (r.get('content') or '').strip()
                    all_reviews.append({
                        'review_id': rid,
                        'text':      text,
                        'rating':    star,
                        'date':      dt.strftime('%Y-%m-%d'),
                        'has_text':  bool(text),
                    })

            except Exception as e:
                # One call failing should not stop the whole run —
                # log it and continue with remaining calls
                log.warning(
                    f'Scraper call failed for {star}★ lang={lang_label}: {e} — skipping'
                )
                continue

    log.info(
        f'Fetch complete: {total_calls} API calls made, '
        f'{total_fetched} raw reviews received, '
        f'{len(all_reviews)} unique 1-2-3★ reviews within last {DAYS_TO_FETCH} days'
    )
    return all_reviews
