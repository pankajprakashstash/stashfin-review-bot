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

    log.info('Step 1/5: Fetching reviews...')
    from bot.fetcher import fetch_reviews
    reviews = fetch_reviews()
    if not reviews:
        log.warning('No reviews fetched — exiting.')
        return

    log.info('Step 2/5: Loading history...')
    from bot.digest import load_history
    history      = load_history()
    prev_buckets = history[-1].get('buckets', []) if history else []
    log.info(f'{len(history)} weeks of history | prev buckets: {[b["name"] for b in prev_buckets] or "none"}')

    log.info('Step 3/5: Gemini — discover buckets + classify...')
    from bot.classifier import discover_buckets, classify_reviews
    buckets    = discover_buckets(reviews, prev_buckets)
    classified = classify_reviews(reviews, buckets)

    log.info('Step 4/5: Building digest...')
    from bot.digest import build_digest, save_digest_to_history
    digest = build_digest(classified, buckets)
    log.info(f'Digest: {digest["total"]} reviews | avg rating: {digest["avg_rating"]}★ | '
             f'buckets: {[b["name"] for b in buckets]}')

    log.info('Step 5/5: Publishing...')
    from bot.detail_page import generate
    generate(digest, 'index.html')

    from bot.email_publisher import publish_via_email
    publish_via_email(digest)

    save_digest_to_history(digest)
    log.info('=== Bot run complete ===')


if __name__ == '__main__':
    main()
