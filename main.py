"""
main.py — StashFin Review Bot entry point.

Modes:
  auto        — detect from day of week: Monday = full run, else scrape only
  full        — scrape + classify + send email (manual trigger)
  scrape_only — scrape and save counts only, no Gemini, no email

Daily scrape (no Gemini): saves raw counts to history for accurate weekly totals.
Monday full run: classifies last 7 days, sends email, updates detail page.
"""
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('ReviewBot')


def _is_monday() -> bool:
    return datetime.now(timezone.utc).weekday() == 0  # 0 = Monday


def run_full():
    """Full run: scrape + classify + email + detail page."""
    log.info('=== FULL RUN: scrape + classify + email ===')

    log.info('Step 1/5: Fetching reviews...')
    from bot.fetcher import fetch_reviews
    reviews = fetch_reviews()
    if not reviews:
        log.warning('No reviews fetched — exiting.')
        return

log.info('Step 2/5: Loading history...')
    from bot.digest import load_history, classified_weeks
    history       = load_history()
    prev_weeks    = classified_weeks(history)
    prev_buckets  = prev_weeks[-1].get('buckets', []) if prev_weeks else []
    log.info(f'{len(history)} weeks stored | prev buckets: {[b["name"] for b in prev_buckets] or "none"}')

    log.info('Step 3/5: Classifying with Gemini...')
    from bot.classifier import discover_buckets, classify_reviews
    buckets    = discover_buckets(reviews, prev_buckets)
    classified = classify_reviews(reviews, buckets)

    log.info('Step 4/5: Building digest...')
    from bot.digest import build_digest, save_digest_to_history
    digest = build_digest(classified, buckets)
    log.info(f'{digest["total"]} reviews | buckets: {[b["name"] for b in buckets]}')

    log.info('Step 5/5: Publishing...')
    from bot.detail_page import generate
    generate(digest, 'index.html')

    from bot.email_publisher import publish_via_email
    publish_via_email(digest)

    save_digest_to_history(digest)
    log.info('=== Full run complete ===')


def run_scrape_only():
    """
    Lightweight daily scrape — no Gemini, no email.
    Saves raw review counts to history for accurate weekly totals.
    """
    log.info('=== SCRAPE ONLY: no Gemini, no email ===')

    from bot.fetcher import fetch_reviews
    reviews = fetch_reviews()

    if not reviews:
        log.warning('No reviews fetched today.')
        return

    # Save a lightweight daily entry to history
    from bot.digest import load_history, save_history
    from datetime import datetime, timezone
    history = load_history()

    star_counts  = reviews[0].get('star_counts', {}) if reviews else {}
    window_start = reviews[0].get('window_start', '') if reviews else ''
    window_end   = reviews[0].get('window_end', '') if reviews else ''
    date_range   = f'{window_start} – {window_end}' if window_start else ''

    daily_entry = {
        'date_range':   date_range,
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'total':        len(reviews),
        'weekly_total': reviews[0].get('weekly_total', 0),
        'star_counts':  star_counts,
        'buckets':      [],
        'by_category':  {},  # no classification yet
    }

    # Only save if not a duplicate date
    if not history or history[-1].get('date_range') != date_range:
        history.append(daily_entry)
        save_history(history)
        log.info(f'Daily entry saved: {len(reviews)} reviews | {date_range}')
    else:
        log.info(f'Entry for {date_range} already exists — skipping duplicate')

    log.info('=== Scrape only complete ===')


def main():
    run_mode = os.environ.get('RUN_MODE', 'auto').lower()

    if run_mode == 'auto':
        if _is_monday():
            log.info('Monday detected — running full workflow')
            run_full()
        else:
            log.info('Non-Monday — running scrape only (no Gemini, no email)')
            run_scrape_only()
    elif run_mode == 'full':
        run_full()
    elif run_mode == 'scrape_only':
        run_scrape_only()
    else:
        log.warning(f'Unknown RUN_MODE "{run_mode}" — defaulting to full run')
        run_full()


if __name__ == '__main__':
    main()
