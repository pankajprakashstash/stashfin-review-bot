"""
fetcher.py
==========
Fetches ALL 1-2-3★ reviews within the date window using pagination.
Counts 4★ and 5★ reviews for weekly total — no text stored, never sent to Gemini.

Pagination fix: instead of one call with a ceiling, fetches batches of 200
using continuation_token until it hits reviews older than DAYS_TO_FETCH.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from google_play_scraper import reviews, Sort
from bot.config import PLAY_PACKAGE_NAME, DAYS_TO_FETCH

log = logging.getLogger(__name__)

BATCH_SIZE = 200   # reviews per paginated call
MAX_PAGES  = 20    # safety cap — 20 × 200 = 4000 max per star rating


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _fetch_star(star: int, cutoff: datetime, seen_ids: set) -> list[dict]:
    """
    Fetch all reviews for one star rating newer than cutoff.
    Paginates until it hits the cutoff date or runs out of reviews.
    Stores full review data including text.
    """
    collected          = []
    continuation_token = None
    page               = 0

    while page < MAX_PAGES:
        kwargs = dict(
            lang              = 'en',
            country           = 'in',
            sort              = Sort.NEWEST,
            count             = BATCH_SIZE,
            filter_score_with = star,
        )
        if continuation_token:
            kwargs['continuation_token'] = continuation_token

        try:
            result, continuation_token = reviews(PLAY_PACKAGE_NAME, **kwargs)
        except Exception as e:
            log.warning(f'Scraper error on {star}★ page {page+1}: {e} — stopping')
            break

        page += 1

        if not result:
            log.info(f'  {star}★ page {page}: no more results')
            break

        hit_cutoff = False
        for r in result:
            dt = r.get('at')
            if not dt:
                continue
            dt = _to_utc(dt)

            if dt < cutoff:
                hit_cutoff = True
                break

            rid = r.get('reviewId', '')
            if not rid or rid in seen_ids:
                continue
            seen_ids.add(rid)

            text = (r.get('content') or '').strip()
            collected.append({
                'review_id': rid,
                'text':      text,
                'rating':    star,
                'date':      dt.strftime('%Y-%m-%d'),
                'has_text':  bool(text),
            })

        log.info(
            f'  {star}★ page {page}: got {len(result)} from Play Store, '
            f'{len(collected)} in window so far'
        )

        if hit_cutoff or not continuation_token:
            break

    return collected


def _count_star(star: int, cutoff: datetime) -> int:
    """
    Count reviews for a star rating within the window.
    No text stored, never sent to Gemini — count only.
    """
    count              = 0
    continuation_token = None
    page               = 0

    while page < MAX_PAGES:
        kwargs = dict(
            lang              = 'en',
            country           = 'in',
            sort              = Sort.NEWEST,
            count             = BATCH_SIZE,
            filter_score_with = star,
        )
        if continuation_token:
            kwargs['continuation_token'] = continuation_token

        try:
            result, continuation_token = reviews(PLAY_PACKAGE_NAME, **kwargs)
        except Exception as e:
            log.warning(f'Count error on {star}★ page {page+1}: {e} — stopping')
            break

        page += 1

        if not result:
            break

        hit_cutoff = False
        for r in result:
            dt = r.get('at')
            if not dt:
                continue
            dt = _to_utc(dt)
            if dt < cutoff:
                hit_cutoff = True
                break
            count += 1

        if hit_cutoff or not continuation_token:
            break

    return count


def fetch_reviews() -> list[dict]:
    cutoff      = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_FETCH)
    seen_ids    = set()
    all_reviews = []

    log.info(f'Fetching 1-2-3★ reviews since {cutoff.date()} with pagination...')

    # ── Fetch full review data for 1, 2, 3 star ───────────────────
    for star in [1, 2, 3]:
        log.info(f'Fetching {star}★ reviews...')
        star_reviews = _fetch_star(star, cutoff, seen_ids)
        all_reviews.extend(star_reviews)
        log.info(f'{star}★ complete: {len(star_reviews)} reviews in window')

    negative_count = len(all_reviews)

    # ── Count only for 4 and 5 star — no text, no Gemini ─────────
    log.info('Counting 4★ reviews (no text stored)...')
    count_4 = _count_star(4, cutoff)
    log.info(f'4★ count: {count_4}')

    log.info('Counting 5★ reviews (no text stored)...')
    count_5 = _count_star(5, cutoff)
    log.info(f'5★ count: {count_5}')

    weekly_total         = negative_count + count_4 + count_5
    positive_count       = count_4 + count_5
    negative_signal_rate = round((negative_count / weekly_total * 100), 1) if weekly_total else 0

    log.info(
        f'Fetch complete — '
        f'Weekly total (all stars): {weekly_total} | '
        f'1-2-3★ captured: {negative_count} | '
        f'4-5★ (count only): {positive_count} | '
        f'Negative signal rate: {negative_signal_rate}%'
    )

    # Attach weekly totals to each review so digest can read them
    for r in all_reviews:
        r['weekly_total']         = weekly_total
        r['weekly_positive_count'] = positive_count
        r['negative_signal_rate'] = negative_signal_rate

    return all_reviews
