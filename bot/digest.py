"""
digest.py
Builds the full weekly digest — counts, trends, spikes, sentiment score,
sub-category breakdown, and verbatim examples.
Loads last week's data from last_run.json for comparison.
"""
from __future__ import annotations
import json
import logging
import os
from collections import defaultdict, Counter
from datetime import datetime, timezone
from bot.classifier import TAXONOMY

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
    exportable = {
        'generated_at':   digest['generated_at'],
        'total':          digest['total'],
        'by_category':    {k: {'count': v['count']} for k, v in digest['by_category'].items()},
        'sentiment_score': digest['sentiment_score'],
    }
    with open(LAST_RUN_FILE, 'w') as f:
        json.dump(exportable, f, indent=2)
    log.info(f'Saved run data to {LAST_RUN_FILE}')


def _sentiment_score(negative: int, total: int) -> float:
    """Score out of 10 — higher is better. 10 = no negative reviews."""
    if total == 0:
        return 10.0
    return round(10 * (1 - negative / total), 1)


def build_digest(reviews: list[dict]) -> dict:
    last = load_last_run()
    prev_category_counts: dict = {k: v.get('count', 0)
                                   for k, v in last.get('by_category', {}).items()}
    prev_total          = last.get('total', 0)
    prev_score          = last.get('sentiment_score', None)
    prev_date           = last.get('generated_at', 'N/A')

    # ── Build counts ──────────────────────────────────────────────
    by_category: dict = defaultdict(lambda: {
        'count': 0, 'sub_categories': defaultdict(int), 'examples': []
    })
    sentiment_counter = Counter()

    for r in reviews:
        cat  = r.get('category', 'Other / Vague')
        sub  = r.get('sub_category', '')
        sent = r.get('sentiment', 'Negative')
        text = r.get('text', '').strip()

        sentiment_counter[sent] += 1
        bucket = by_category[cat]
        bucket['count'] += 1
        bucket['sub_categories'][sub] += 1
        if text and len(bucket['examples']) < 3:
            snippet = text[:200] + ('…' if len(text) > 200 else '')
            bucket['examples'].append(f'[{r["rating"]}★] {snippet}')

    # ── Compute deltas ────────────────────────────────────────────
    for cat, data in by_category.items():
        data['delta']         = data['count'] - prev_category_counts.get(cat, 0)
        data['sub_categories'] = dict(data['sub_categories'])

    # ── Sentiment score ───────────────────────────────────────────
    neg   = sentiment_counter.get('Negative', 0)
    total = len(reviews)
    score = _sentiment_score(neg, total)

    # ── Top issues (exclude no-text bucket) ───────────────────────
    top_issues = sorted(
        [(cat, data['count'], data['delta'])
         for cat, data in by_category.items()
         if cat not in ('Uncategorized / No Text',) and data['count'] > 0],
        key=lambda x: -x[1]
    )

    # ── Spike detection: new or jumped >50% vs last week ──────────
    spikes = []
    for cat, count, delta in top_issues:
        prev = prev_category_counts.get(cat, 0)
        if prev == 0 and count >= 3:
            spikes.append((cat, count, 'NEW this week'))
        elif prev > 0 and delta > 0 and (delta / prev) >= 0.5:
            pct = int((delta / prev) * 100)
            spikes.append((cat, count, f'↑ {pct}% spike vs last week'))

    return {
        'generated_at':    datetime.now(timezone.utc).strftime('%d %b %Y'),
        'prev_date':       prev_date,
        'total':           total,
        'prev_total':      prev_total,
        'total_delta':     total - prev_total,
        'by_sentiment':    dict(sentiment_counter),
        'by_category':     dict(by_category),
        'top_issues':      top_issues,
        'spikes':          spikes,
        'sentiment_score': score,
        'prev_score':      prev_score,
        'raw':             reviews,
    }


def filter_for_team(digest: dict, categories: list | None) -> dict:
    if categories is None:
        return digest
    filtered_reviews = [r for r in digest['raw'] if r.get('category') in categories]
    filtered_cats    = {k: v for k, v in digest['by_category'].items() if k in categories}
    filtered_top     = [(c, n, d) for c, n, d in digest['top_issues'] if c in categories]
    filtered_spikes  = [(c, n, l) for c, n, l in digest['spikes'] if c in categories]
    neg = sum(1 for r in filtered_reviews if r.get('sentiment') == 'Negative')
    return {
        **digest,
        'total':        len(filtered_reviews),
        'by_category':  filtered_cats,
        'top_issues':   filtered_top,
        'spikes':       filtered_spikes,
        'sentiment_score': _sentiment_score(neg, len(filtered_reviews)),
        'raw':          filtered_reviews,
    }
