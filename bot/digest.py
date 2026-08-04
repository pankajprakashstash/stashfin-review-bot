"""
digest.py — Weekly digest builder with rolling history.
"""
from __future__ import annotations
import json
import logging
import os
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from bot.config import DAYS_TO_FETCH, MAX_HISTORY_WEEKS, ISSUE_COLORS

log     = logging.getLogger(__name__)
HISTORY = 'history.json'
LAST    = 'last_run.json'
EXCLUDE = {'Uncategorized / No Text', 'Irrelevant / Gibberish', 'Positive Feedback'}


def load_history() -> list[dict]:
    if os.path.exists(HISTORY):
        try:
            with open(HISTORY) as f:
                return json.load(f).get('weeks', [])
        except Exception:
            pass
    if os.path.exists(LAST):
        try:
            with open(LAST) as f:
                old = json.load(f)
                return [old] if old else []
        except Exception:
            pass
    return []


def save_history(weeks: list[dict]) -> None:
    """
    Trim by CLASSIFIED week count, not raw entry count. Daily scrape_only
    entries (buckets: []) get appended most days and would otherwise
    dominate a simple weeks[-MAX_HISTORY_WEEKS:] slice, silently pushing
    out older classified weeks after just ~1 real week of runs.
    """
    classified = [w for w in weeks if w.get('buckets')]
    keep       = classified[-MAX_HISTORY_WEEKS:]

    if keep:
        cutoff  = keep[0].get('generated_at', '')
        trimmed = [w for w in weeks if w.get('generated_at', '') >= cutoff]
    else:
        # No classified weeks yet — just cap raw daily entries reasonably.
        trimmed = weeks[-(MAX_HISTORY_WEEKS * 7):]

    with open(HISTORY, 'w') as f:
        json.dump({'weeks': trimmed}, f, indent=2)
    if trimmed:
        with open(LAST, 'w') as f:
            json.dump(trimmed[-1], f, indent=2)
    log.info(f'History saved ({len(trimmed)} weeks)')


def classified_weeks(history: list[dict]) -> list[dict]:
    """
    Return only entries that came from a FULL run (Gemini-classified,
    has real buckets). Daily scrape_only entries have empty 'buckets'
    and would otherwise dilute the trend/table with blank columns.
    """
    return [wk for wk in history if wk.get('buckets')]


def build_digest(reviews: list[dict], buckets: list[dict]) -> dict:
    history       = load_history()
    classified    = classified_weeks(history)
    prev_week     = classified[-1] if classified else {}
    prev_counts   = {k: v.get('count', 0) for k, v in prev_week.get('by_category', {}).items()}
    prev_total    = prev_week.get('total', 0)
    prev_date     = prev_week.get('date_range', None)

    # Get date range from fetcher (window_start → window_end, today excluded)
    if reviews:
        window_start = reviews[0].get('window_start', '')
        window_end   = reviews[0].get('window_end', '')
        date_range   = f'{window_start} – {window_end}' if window_start and window_end else ''
    else:
        now        = datetime.now(timezone.utc)
        yesterday  = now - timedelta(days=1)
        start      = yesterday - timedelta(days=DAYS_TO_FETCH - 1)
        date_range = f'{start.strftime("%d %b %Y")} – {yesterday.strftime("%d %b %Y")}'

    # Weekly stats
    weekly_total = reviews[0].get('weekly_total', 0) if reviews else 0
    avg_rating   = reviews[0].get('avg_rating', 0.0)  if reviews else 0.0
    signal_rate  = reviews[0].get('signal_rate', 0)   if reviews else 0
    star_counts  = reviews[0].get('star_counts', {})  if reviews else {}

    # Aggregate
    by_category   = defaultdict(lambda: {'count': 0, 'sub_categories': defaultdict(int),
                                          'examples': [], 'team_tag': '', 'prev_count': 0})
    sentiment_ctr = Counter()
    team_lookup   = {b['name']: b.get('team_tag', '') for b in buckets}

    for r in reviews:
        cat  = r.get('category', 'General Complaints')
        sent = r.get('sentiment', 'Negative')
        text = r.get('text', '').strip()
        rc   = r.get('root_cause', '')

        sentiment_ctr[sent] += 1
        bkt = by_category[cat]
        bkt['count']     += 1
        bkt['team_tag']   = team_lookup.get(cat, r.get('team_tag', ''))
        bkt['prev_count'] = prev_counts.get(cat, 0)
        if rc:
            bkt['sub_categories'][rc[:80] + ('…' if len(rc) > 80 else '')] += 1
        if text and len(bkt['examples']) < 3:
            bkt['examples'].append(f'[{r["rating"]}★] {text[:180]}{"…" if len(text)>180 else ""}')

    for cat, data in by_category.items():
        data['delta']          = data['count'] - prev_counts.get(cat, 0)
        data['sub_categories'] = dict(data['sub_categories'])

    total = len(reviews)

    top_issues = sorted(
        [(cat, d['count'], d['delta'], d['team_tag'], d['prev_count'])
         for cat, d in by_category.items()
         if cat not in EXCLUDE and d['count'] > 0],
        key=lambda x: -x[1]
    )

    color_map = {cat: ISSUE_COLORS[min(i, len(ISSUE_COLORS)-1)]
                 for i, (cat, *_) in enumerate(top_issues)}

    spikes = []
    for cat, count, delta, tag, prev in top_issues:
        if prev == 0 and count >= 3:
            spikes.append((cat, count, 'NEW'))
        elif prev > 0 and delta > 0 and delta / prev >= 0.5:
            spikes.append((cat, count, f'+{int(delta/prev*100)}%'))

    trend_data = {}
    for cat, count, *_ in top_issues:
        weekly = []
        for wk in classified[-7:]:
            wk_count = wk.get('by_category', {}).get(cat, {}).get('count', 0)
            weekly.append({'date': wk.get('date_range', ''), 'count': wk_count})
        weekly.append({'date': date_range, 'count': count})
        trend_data[cat] = weekly

    current_entry = {
        'date_range':   date_range,
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'total':        total,
        'weekly_total': weekly_total,
        'avg_rating':   avg_rating,
        'signal_rate':  signal_rate,
        'star_counts':  star_counts,
        'buckets':      [{'name': b['name'], 'team_tag': b.get('team_tag', '')} for b in buckets],
        'by_category':  {cat: {'count': d['count']} for cat, d in by_category.items()},
    }

    return {
        'date_range':      date_range,
        'prev_date_range': prev_date,
        'generated_at':    datetime.now(timezone.utc).strftime('%d %b %Y'),
        'total':           total,
        'prev_total':      prev_total,
        'total_delta':     total - prev_total,
        'weekly_total':    weekly_total,
        'avg_rating':      avg_rating,
        'prev_avg_rating': prev_week.get('avg_rating', None),
        'signal_rate':     signal_rate,
        'star_counts':     star_counts,
        'by_sentiment':    dict(sentiment_ctr),
        'by_category':     dict(by_category),
        'top_issues':      top_issues,
        'color_map':       color_map,
        'spikes':          spikes,
        'trend_data':      trend_data,
        'history':         history,          # raw, incl. daily entries — used for persistence
        'classified_history': classified,    # full-run weeks only — used for trend/table display
        'current_entry':   current_entry,
        'buckets':         buckets,
        'raw':             reviews,
    }


def save_digest_to_history(digest: dict) -> None:
    history = list(digest['history'])
    current = digest['current_entry']

    # Defensive de-dupe: if the last stored entry is already this same
    # date_range (e.g. workflow triggered twice for the same week),
    # overwrite it instead of adding a duplicate column/point.
    if history and history[-1].get('date_range') == current.get('date_range'):
        log.warning(f'Duplicate run detected for {current["date_range"]} — overwriting last entry')
        history[-1] = current
    else:
        history.append(current)

    save_history(history)
