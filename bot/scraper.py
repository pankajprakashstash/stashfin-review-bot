"""
scraper.py — Play Store Review Scraper
Fetches ALL reviews per star rating with no count ceiling.
Paginates until date cutoff is hit or pages are exhausted.
4★ and 5★ counted only — no text, no Gemini cost.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from google_play_scraper import reviews as gps_reviews, Sort
from bot.config import PLAY_PACKAGE_NAME

log = logging.getLogger(__name__)

PAGE_SIZE  = 200
MAX_PAGES  = 30       # 30 × 200 = 6000 per star — well above any weekly volume
RETRY_WAIT = 3


def _to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _fetch_star(star: int, cutoff: datetime, seen_ids: set) -> list[dict]:
    """Fetch all reviews for one star rating newer than cutoff. No count ceiling."""
    collected = []
    token     = None
    page      = 0

    while page < MAX_PAGES:     # ← only MAX_PAGES limit, no review count ceiling
        kwargs = dict(lang='en', country='in', sort=Sort.NEWEST,
                      count=PAGE_SIZE, filter_score_with=star)
        if token:
            kwargs['continuation_token'] = token

        for attempt in range(3):
            try:
                result, token = gps_reviews(PLAY_PACKAGE_NAME, **kwargs)
                break
            except Exception as e:
                if attempt == 2:
                    log.warning(f'{star}★ page {page+1} failed: {e}')
                    return collected
                time.sleep(RETRY_WAIT * (attempt + 1))

        page += 1

        if not result:
            log.info(f'  {star}★ p{page}: empty — done')
            break

        hit_cutoff    = False
        new_this_page = 0
        for r in result:
            dt = r.get('at')
            if not dt:
                continue
            dt = _to_utc(dt)
            if dt < cutoff:
                hit_cutoff = True
                break
            rid  = r.get('reviewId', '')
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
            new_this_page += 1

        log.info(f'  {star}★ p{page}: +{new_this_page} in window (total {len(collected)})')

        if hit_cutoff or not token:
            break

    return collected


def _count_star(star: int, cutoff: datetime) -> int:
    """Count reviews for one star rating — no text, no Gemini cost."""
    count = 0
    token = None
    page  = 0

    while page < MAX_PAGES:     # ← same, no count ceiling
        kwargs = dict(lang='en', country='in', sort=Sort.NEWEST,
                      count=PAGE_SIZE, filter_score_with=star)
        if token:
            kwargs['continuation_token'] = token
        try:
            result, token = gps_reviews(PLAY_PACKAGE_NAME, **kwargs)
        except Exception as e:
            log.warning(f'{star}★ count p{page+1} error: {e}')
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

        if hit_cutoff or not token:
            break

    return count


def scrape(cutoff: datetime) -> tuple[list[dict], dict[int, int]]:
    """
    Fetch all 1-2-3★ reviews + count 4★ and 5★.
    Returns (reviews, star_counts) where star_counts = {1:n, 2:n, 3:n, 4:n, 5:n}
    """
    seen_ids    = set()
    all_reviews = []
    star_counts = {}

    for star in [1, 2, 3]:
        log.info(f'Fetching {star}★ reviews...')
        sr = _fetch_star(star, cutoff, seen_ids)
        all_reviews.extend(sr)
        star_counts[star] = len(sr)
        log.info(f'{star}★ done: {len(sr)} reviews in window')

    for star in [4, 5]:
        log.info(f'Counting {star}★ (no text)...')
        star_counts[star] = _count_star(star, cutoff)
        log.info(f'{star}★ count: {star_counts[star]}')

    log.info(f'Scrape complete — star counts: {star_counts}')
    return all_reviews, star_counts
