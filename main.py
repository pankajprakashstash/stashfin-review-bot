"""
main.py — StashFin Review Bot entry point.
Automated via GitHub Actions every Monday 9am IST.
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('ReviewBot')


def main():
    log.info('=== StashFin Review Bot starting ===')

    # Step 1 — Fetch reviews
    log.info('Step 1/5: Fetching reviews...')
    from bot.fetcher import fetch_reviews
    reviews = fetch_reviews()
    if not reviews:
        log.warning('No reviews fetched — exiting.')
        return

    # ── Scraper diagnostic — compare with Play Console ─────────────
    star_counts = reviews[0].get('star_counts', {}) if reviews else {}
    log.info('=' * 50)
    log.info('SCRAPER DIAGNOSTIC — compare with Play Console')
    log.info(f'1★ : {star_counts.get(1, 0)}')
    log.info(f'2★ : {star_counts.get(2, 0)}')
    log.info(f'3★ : {star_counts.get(3, 0)}')
    log.info(f'4★ : {star_counts.get(4, 0)}')
    log.info(f'5★ : {star_counts.get(5, 0)}')
    log.info(f'TOTAL SCRAPED     : {sum(star_counts.values())}')
    log.info(f'1-2-3★ with text  : {sum(1 for r in reviews if r.get("has_text"))}')
    log.info(f'1-2-3★ no text    : {sum(1 for r in reviews if not r.get("has_text"))}')
    log.info(f'Avg rating        : {reviews[0].get("avg_rating", 0)}★')
    log.info('=' * 50)

    # Step 2 — Load history
    log.info('Step 2/5: Loading history...')
    from bot.digest import load_history
    history      = load_history()
    prev_buckets = history[-1].get('buckets', []) if history else []
    log.info(f'{len(history)} weeks of history stored')
    log.info(f'Prev buckets: {[b["name"] for b in prev_buckets] or "none (first run)"}')

    # Step 3 — Discover buckets + classify
    log.info('Step 3/5: Gemini — discover buckets + classify...')
    from bot.classifier import discover_buckets, classify_reviews
    buckets    = discover_buckets(reviews, prev_buckets)
    classified = classify_reviews(reviews, buckets)

    # Step 4 — Build digest
    log.info('Step 4/5: Building digest...')
    from bot.digest import build_digest, save_digest_to_history
    digest = build_digest(classified, buckets)
    log.info(
        f'Digest: {digest["total"]} reviews | '
        f'Avg rating: {digest["avg_rating"]}★ | '
        f'Buckets: {[b["name"] for b in buckets]}'
    )

    # Step 5 — Publish
    log.info('Step 5/5: Publishing...')
    from bot.detail_page import generate
    generate(digest, 'index.html')

    from bot.email_publisher import publish_via_email
    publish_via_email(digest)

    save_digest_to_history(digest)
    log.info('=== Bot run complete ===')


if __name__ == '__main__':
    main()
