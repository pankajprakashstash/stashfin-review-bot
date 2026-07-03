import logging
import random
import time
from datetime import datetime, timezone

from google_play_scraper import reviews as gps_reviews, Sort
from bot.config import PLAY_PACKAGE_NAME, MAX_REVIEWS_PER_STAR

log = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 15
RETRY_WAIT = 5


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sleep():
    """Throttle requests to reduce Play Store rate limiting."""
    time.sleep(random.uniform(1.0, 2.0))


def _fetch_reviews_page(star: int, token=None):
    kwargs = {
        "lang": "en",
        "country": "in",
        "sort": Sort.NEWEST,
        "count": PAGE_SIZE,
        "filter_score_with": star,
    }

    if token:
        kwargs["continuation_token"] = token

    for attempt in range(3):
        try:
            result, next_token = gps_reviews(
                PLAY_PACKAGE_NAME,
                **kwargs,
            )

            _sleep()
            return result, next_token

        except Exception:
            log.exception(
                f"{star}★ request failed "
                f"(attempt {attempt + 1}/3)"
            )

            if attempt == 2:
                raise

            time.sleep(RETRY_WAIT * (attempt + 1))

    return [], None


def _fetch_star(
    star: int,
    cutoff: datetime,
    seen_ids: set,
) -> list[dict]:

    collected = []
    token = None

    for page in range(1, MAX_PAGES + 1):

        if len(collected) >= MAX_REVIEWS_PER_STAR:
            break

        try:
            result, token = _fetch_reviews_page(star, token)

        except Exception:
            log.error(f"{star}★ stopped at page {page}")
            break

        if not result:
            log.info(f"{star}★ page {page}: no results")
            break

        page_new = 0
        page_in_window = 0

        for r in result:

            dt = r.get("at")
            if not dt:
                continue

            dt = _to_utc(dt)

            if dt < cutoff:
                continue

            page_in_window += 1

            rid = r.get("reviewId")
            if not rid or rid in seen_ids:
                continue

            seen_ids.add(rid)

            text = (r.get("content") or "").strip()

            collected.append(
                {
                    "review_id": rid,
                    "text": text,
                    "rating": star,
                    "date": dt.strftime("%Y-%m-%d"),
                    "has_text": bool(text),
                }
            )

            page_new += 1

            if len(collected) >= MAX_REVIEWS_PER_STAR:
                break

        log.info(
            f"{star}★ page={page} "
            f"results={len(result)} "
            f"new={page_new} "
            f"total={len(collected)} "
            f"token={'yes' if token else 'no'}"
        )

        # Entire page is older than cutoff
        if page_in_window == 0:
            log.info(
                f"{star}★ page {page} is fully older "
                f"than cutoff. Stopping."
            )
            break

        if not token:
            break

    return collected


def _count_star(
    star: int,
    cutoff: datetime,
) -> int:

    total = 0
    token = None

    for page in range(1, MAX_PAGES + 1):

        try:
            result, token = _fetch_reviews_page(star, token)

        except Exception:
            log.error(f"{star}★ count failed at page {page}")
            break

        if not result:
            break

        page_count = 0

        for r in result:

            dt = r.get("at")
            if not dt:
                continue

            dt = _to_utc(dt)

            if dt < cutoff:
                continue

            total += 1
            page_count += 1

        log.info(
            f"{star}★ count "
            f"page={page} "
            f"page_count={page_count} "
            f"running_total={total}"
        )

        if page_count == 0:
            break

        if not token:
            break

    return total


def scrape(
    cutoff: datetime,
) -> tuple[list[dict], dict[int, int]]:

    seen_ids = set()
    reviews = []
    star_counts = {}

    for star in (1, 2, 3):

        log.info(f"Scraping {star}★ reviews")

        star_reviews = _fetch_star(
            star=star,
            cutoff=cutoff,
            seen_ids=seen_ids,
        )

        reviews.extend(star_reviews)

        star_counts[star] = len(star_reviews)

        log.info(
            f"{star}★ completed "
            f"with {len(star_reviews)} reviews"
        )

    log.info("Counting 4★ reviews")
    star_counts[4] = _count_star(4, cutoff)

    log.info("Counting 5★ reviews")
    star_counts[5] = _count_star(5, cutoff)

    log.info(f"Final star counts: {star_counts}")

    return reviews, star_counts
