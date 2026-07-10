"""
scraper.py — Play Store Review Scraper
Fetches 1-2-3★ reviews between cutoff and upper_bound.
4★ and 5★ are counted only — no text, no Gemini cost.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from google_play_scraper import reviews as gps_reviews, Sort
from bot.config import PLAY_PACKAGE_NAME

log = logging.getLogger(__name__)

PAGE_SIZE = 200
MAX_PAGES = 30
RETRY_WAIT = 3


def _to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _fetch_star(star: int, cutoff: datetime, upper: datetime,
                seen_ids: set) -> list[dict]:
    """Fetch reviews for one star rating between cutoff and upper bound."""
    collected = []
    token     = None
    page      = 0

    while page < MAX_PAGES:
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
                    log.warning(f'{star}★ p{page+1} failed: {e}')
                    return collected
                time.sleep(RETRY_WAIT * (attempt + 1))

        page += 1
        if not result:
            break

        hit_cutoff    = False
        new_this_page = 0

        for r in result:
            dt = r.get('at')
            if not dt:
                continue
            dt = _to_utc(dt)

            # Skip reviews newer than upper bound (today)
            if dt > upper:
                continue

            # Stop when we go past the window
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


def _count_star(star: int, cutoff: datetime, upper: datetime) -> int:
    """Count reviews for one star rating in window — no text stored."""
    count = 0
    token = None
    page  = 0

    while page < MAX_PAGES:
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
            if dt > upper:
                continue
            if dt < cutoff:
                hit_cutoff = True
                break
            count += 1

        if hit_cutoff or not token:
            break

    return count


def scrape(cutoff: datetime,
           upper: datetime) -> tuple[list[dict], dict[int, int]]:
    """
    Fetch 1-2-3★ reviews between cutoff and upper.
    Count 4★ and 5★ only.
    Returns (reviews, star_counts)
    """
    seen_ids    = set()
    all_reviews = []
    star_counts = {}

    for star in [1, 2, 3]:
        log.info(f'Fetching {star}★...')
        sr = _fetch_star(star, cutoff, upper, seen_ids)
        all_reviews.extend(sr)
        star_counts[star] = len(sr)
        log.info(f'{star}★ done: {len(sr)}')

    for star in [4, 5]:
        log.info(f'Counting {star}★...')
        star_counts[star] = _count_star(star, cutoff, upper)
        log.info(f'{star}★ count: {star_counts[star]}')

    log.info(f'Scrape complete: {star_counts}')
    return all_reviews, star_counts
