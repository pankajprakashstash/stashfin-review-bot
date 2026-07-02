"""
main.py — StashFin Review Bot entry point.
Run directly: python main.py
Or automated via GitHub Actions every week.
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

    # Step 1 — Fetch
    log.info('Step 1/4: Fetching reviews from Play Store...')
    from bot.fetcher import fetch_reviews
    reviews = fetch_reviews()
    if not reviews:
        log.warning('No reviews fetched — nothing to process. Exiting.')
        return

    # Step 2 — Classify
    log.info('Step 2/4: Classifying reviews with Gemini...')
    from bot.classifier import classify_reviews
    classified = classify_reviews(reviews)

    # Step 3 — Build digest
    log.info('Step 3/4: Building digest...')
    from bot.digest import build_digest, save_last_run
    digest = build_digest(classified)

    log.info(f'Digest summary: {digest["total"]} reviews | '
             f'Negative: {digest["by_sentiment"].get("Negative",0)} | '
             f'Sentiment score: {digest["sentiment_score"]}/10')
    if digest['spikes']:
        log.info(f'Spikes detected: {[s[0] for s in digest["spikes"]]}')

    # Step 4 — Publish
    log.info('Step 4/4: Sending emails...')
    from bot.email_publisher import publish_via_email
    publish_via_email(digest)

    # Save this run's data for next week's trend comparison
    save_last_run(digest)
    log.info('=== Bot run complete ===')


if __name__ == '__main__':
    main()
