"""
fetcher.py — Entry point for data collection.
Calls scraper, calculates average rating from per-star counts,
attaches all weekly stats to each review for digest to read.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from bot.config import DAYS_TO_FETCH
from bot.scraper import scrape

log = logging.getLogger(__name__)


def fetch_reviews() -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_FETCH)
    log.info(f'Fetching reviews since {cutoff.date()} (last {DAYS_TO_FETCH} days)')

    reviews, star_counts = scrape(cutoff)

    # Weekly totals
    neg_count    = len(reviews)                              # 1+2+3★ with text
    count_4      = star_counts.get(4, 0)
    count_5      = star_counts.get(5, 0)
    weekly_total = neg_count + count_4 + count_5
    signal_rate  = round(neg_count / weekly_total * 100, 1) if weekly_total else 0

    # Weighted average rating — accurate because we know exact count per star
    c1, c2, c3 = star_counts.get(1,0), star_counts.get(2,0), star_counts.get(3,0)
    if weekly_total:
        avg_rating = round((1*c1 + 2*c2 + 3*c3 + 4*count_4 + 5*count_5) / weekly_total, 1)
    else:
        avg_rating = 0.0

    log.info(
        f'Done — 1-2-3★: {neg_count} | 4★: {count_4} | 5★: {count_5} | '
        f'Total: {weekly_total} | Avg rating: {avg_rating}★ | Signal rate: {signal_rate}%'
    )

    for r in reviews:
        r['weekly_total']  = weekly_total
        r['star_counts']   = star_counts
        r['avg_rating']    = avg_rating
        r['signal_rate']   = signal_rate

    return reviews
