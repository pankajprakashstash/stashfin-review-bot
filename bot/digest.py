"""
digest.py
Builds the weekly digest with counts, trends, spikes, and sentiment score.
Stores discovered buckets in last_run.json so classifier can reference them next week.
"""
from __future__ import annotations
import json
import logging
import os
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from bot.config import DAYS_TO_FETCH

log = logging.getLogger(__name__)
LAST_RUN_FILE = 'last_run.json'


def load_last_run() -> dict:
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_last_run(digest: dict) -> None:
    with open(LAST_RUN_FILE, 'w') as f:
        json.dump({
            'generated_at':    digest['generated_at'],
            'date_range':      digest['date_range'],
            'total':           digest['total'],
            'sentiment_score': digest['sentiment_score'],
            'by_category':     {k: {'count': v['count']} for k, v in digest['by_category'].items()},
            'buckets':         digest.get('buckets', []),
        }, f, indent=2)
    log.info(f'Saved run data to {LAST_RUN_FILE}')


def _score(negative: int, total: int) -> float:
    if total == 0: return 10.0
    return round(10 * (1 - negative / total), 1)


def build_digest(reviews: list[dict], buckets: list[dict]) -> dict:
    last            = load_last_run()
    prev_cat_counts = {k: v.get('count', 0) for k, v in last.get('by_category', {}).items()}
    prev_total      = last.get('total', 0)
    prev_score      = last.get('sentiment_score', None)
    prev_date_range = last.get('date_range', 'N/A')

    now        = datetime.now(timezone.utc)
    start      = now - timedelta(days=DAYS_TO_FETCH)
    date_range = f'{start.strftime("%d %b")} – {now.strftime("%d %b %Y")}'

    # ── Aggregate ─────────────────────────────────────────────────
    by_category: dict = defaultdict(lambda: {
        'count': 0, 'sub_categories': defaultdict(int), 'examples': [], 'team_tag': ''
    })
    sentiment_counter = Counter()

    # Build team_tag lookup from buckets
    team_lookup = {b['name']: b.get('team_tag', '') for b in buckets}

    for r in reviews:
        cat  = r.get('category', 'General Complaints')
        sent = r.get('sentiment', 'Negative')
        text = r.get('text', '').strip()
        rc   = r.get('root_cause', '')

        sentiment_counter[sent] += 1
        bucket = by_category[cat]
        bucket['count'] += 1
        bucket['team_tag'] = team_lookup.get(cat, r.get('team_tag', ''))

        # Use root_cause as sub-category label (dynamic, from Gemini)
        if rc:
            short_rc = rc[:80] + ('…' if len(rc) > 80 else '')
            bucket['sub_categories'][short_rc] += 1

        if text and len(bucket['examples']) < 3:
            snippet = text[:180] + ('…' if len(text) > 180 else '')
            bucket['examples'].append(f'[{r["rating"]}★] {snippet}')

    for cat, data in by_category.items():
        data['delta']          = data['count'] - prev_cat_counts.get(cat, 0)
        data['sub_categories'] = dict(data['sub_categories'])

    neg   = sentiment_counter.get('Negative', 0)
    total = len(reviews)
    score = _score(neg, total)

    top_issues = sorted(
        [(cat, data['count'], data['delta'], data['team_tag'])
         for cat, data in by_category.items()
         if cat != 'Uncategorized / No Text' and data['count'] > 0],
        key=lambda x: -x[1]
    )

    spikes = []
    for cat, count, delta, tag in top_issues:
        prev = prev_cat_counts.get(cat, 0)
        if prev == 0 and count >= 3:
            spikes.append((cat, count, 'NEW this week', tag))
        elif prev > 0 and delta > 0 and (delta / prev) >= 0.5:
            spikes.append((cat, count, f'↑ {int((delta/prev)*100)}% spike', tag))

    return {
        'generated_at':    now.strftime('%d %b %Y'),
        'date_range':      date_range,
        'prev_date_range': prev_date_range,
        'total':           total,
        'prev_total':      prev_total,
        'total_delta':     total - prev_total,
        'by_sentiment':    dict(sentiment_counter),
        'by_category':     dict(by_category),
        'top_issues':      top_issues,   # (cat, count, delta, team_tag)
        'spikes':          spikes,        # (cat, count, label, team_tag)
        'sentiment_score': score,
        'prev_score':      prev_score,
        'buckets':         buckets,
        'raw':             reviews,
    }
