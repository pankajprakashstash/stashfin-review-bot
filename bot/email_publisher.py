"""
email_publisher.py — Executive email with real trend line chart.

Trend line solution:
  QuickChart.io renders Chart.js charts server-side → returns a PNG.
  Email embeds it as a plain <img> tag → works in ALL email clients
  (Gmail, Outlook, mobile, everything). No JavaScript needed.
  Free service, no API key required. Chart data: just review counts (no PII).

Card design (matches reference):
  ┌─────────────────────────────────┐
  │ Category Name          (header) │
  ├──────────────┬──────────────────┤
  │   18         │ • Keyword one    │
  │   ↑ +5       │ • Keyword two    │
  │  ▁▂▄▅▇      │                  │
  └──────────────┴──────────────────┘

Max 6 cards. Broader categories enforced in classifier.py.
"""
from __future__ import annotations
import json
import logging
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bot.config import (GMAIL_SENDER, GMAIL_APP_PASSWORD, EMAIL_ALL,
                        PAGES_URL, BRAND_CORAL, BRAND_BLUE,
                        BRAND_CORAL_LT, BRAND_BLUE_LT)

log      = logging.getLogger(__name__)
EXCLUDE  = {'Uncategorized / No Text', 'Irrelevant / Gibberish', 'Positive Feedback'}
MAX_CARDS = 6


# ── Colour helpers ─────────────────────────────────────────────────

def _lighten(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    r2 = int(r + (255-r)*factor)
    g2 = int(g + (255-g)*factor)
    b2 = int(b + (255-b)*factor)
    return f'#{r2:02x}{g2:02x}{b2:02x}'


def _delta_html(n: int) -> str:
    if n > 0:  return f'<span style="color:#CC0000;font-weight:700;">↑ +{n}</span>'
    if n < 0:  return f'<span style="color:#007A45;font-weight:700;">↓ {n}</span>'
    return '<span style="color:#999;">→</span>'


# ── QuickChart trend line ──────────────────────────────────────────

def _trend_chart_url(digest: dict) -> str:
    """
    Build a QuickChart.io URL that renders a Chart.js line chart as PNG.
    QuickChart renders server-side → returns image → works in all email clients.
    Free, no auth, no PII (only review counts).
    Returns empty string if not enough history for a meaningful chart.
    """
    history    = digest.get('history', [])
    top_issues = [(c,n,d,t,p) for c,n,d,t,p in digest['top_issues']
                  if c not in EXCLUDE][:5]
    trend_data = digest.get('trend_data', {})
    color_map  = digest.get('color_map', {})

    if len(history) < 1 or not top_issues:
        return ''

    # Week labels — short format from first category's series
    first_series = trend_data.get(top_issues[0][0], [])
    week_labels  = []
    for pt in first_series:
        dr    = pt.get('date', '')
        short = dr.split('–')[0].strip() if '–' in dr else dr[:8]
        week_labels.append(short)

    if len(week_labels) < 2:
        return ''

    # Datasets — one per issue
    datasets = []
    for cat, *_ in top_issues:
        color  = color_map.get(cat, '#888')
        series = trend_data.get(cat, [])
        values = [pt.get('count', 0) for pt in series]
        if len(values) != len(week_labels):
            continue
        label  = cat[:18] + ('…' if len(cat) > 18 else '')
        datasets.append({
            'label':           label,
            'data':            values,
            'borderColor':     color,
            'backgroundColor': color + '20',
            'fill':            False,
            'tension':         0.3,
            'pointRadius':     4,
            'borderWidth':     2.5,
        })

    if not datasets:
        return ''

    chart_config = {
        'type': 'line',
        'data': {
            'labels':   week_labels,
            'datasets': datasets,
        },
        'options': {
            'scales': {
                'y': {
                    'beginAtZero': True,
                    'grid': {'color': '#F0F0F0'},
                    'ticks': {'font': {'size': 11}},
                },
                'x': {
                    'grid': {'color': '#F0F0F0'},
                    'ticks': {'font': {'size': 10}},
                },
            },
            'plugins': {
                'legend': {
                    'position': 'bottom',
                    'labels':   {
                        'font':     {'size': 10},
                        'boxWidth': 12,
                        'padding':  10,
                    },
                },
            },
        },
    }

    config_str = json.dumps(chart_config, separators=(',', ':'))
    encoded    = urllib.parse.quote(config_str, safe='')
    # w=540 matches email width, h=200 is compact, bkg=white for clean look
    return f'https://quickchart.io/chart?w=540&h=200&bkg=white&c={encoded}'


# ── Bottom-aligned sparkline ───────────────────────────────────────

def _sparkline(counts: list[int], color: str) -> str:
    """Nested-table sparkline — bottom-aligned, works in all email clients."""
    if not counts:
        return ''
    max_c = max(counts) or 1
    MAX_H = 18
    n     = len(counts)
    cells = ''
    for i, c in enumerate(counts):
        bar_h  = max(2, int((c / max_c) * MAX_H))
        gap_h  = MAX_H - bar_h
        factor = max(0.0, (n - 1 - i) * 0.17)
        bg     = _lighten(color, factor)
        cells += (
            f'<td style="vertical-align:bottom;padding:0 1px 0 0;">'
            f'<table cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td style="height:{gap_h}px;width:7px;font-size:0;">&nbsp;</td></tr>'
            f'<tr><td style="height:{bar_h}px;width:7px;background:{bg};'
            f'font-size:0;line-height:0;">&nbsp;</td></tr>'
            f'</table></td>'
        )
    return (f'<table cellpadding="0" cellspacing="0" border="0" '
            f'style="height:{MAX_H}px;margin-top:8px;">'
            f'<tr style="vertical-align:bottom;">{cells}</tr></table>')


# ── Issue card ─────────────────────────────────────────────────────

def _issue_card(cat: str, count: int, delta: int,
                color: str, is_new: bool,
                spark_counts: list[int], keywords: list[str]) -> str:
    short   = cat[:20] + ('…' if len(cat) > 20 else '')
    hdr_col = '#00875A' if is_new else color
    num_col = '#007A45' if is_new else color
    spark   = _sparkline(spark_counts, color)

    if is_new:
        delta_cell = ('<span style="background:#00875A;color:#fff;font-size:9px;'
                      'padding:2px 7px;border-radius:3px;font-weight:700;">NEW</span>')
    else:
        delta_cell = _delta_html(delta)

    kw_rows = ''.join(
        f'<div style="font-size:10px;color:#555;padding:3px 0;line-height:1.4;">'
        f'• {kw[:28]}{"…" if len(kw)>28 else ""}</div>'
        for kw in keywords[:2]
    ) or '<div style="font-size:10px;color:#CCC;">—</div>'

    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border:1.5px solid {hdr_col};border-radius:8px;'
        f'overflow:hidden;background:#fff;">'
        # Header
        f'<tr><td colspan="2" style="background:{hdr_col};padding:7px 12px;'
        f'border-radius:6px 6px 0 0;">'
        f'<span style="color:#fff;font-size:10px;font-weight:600;">{short}</span>'
        f'</td></tr>'
        # Body: left = number + delta + sparkline, right = keywords
        f'<tr>'
        f'<td width="52%" valign="top" style="padding:10px 8px 10px 12px;">'
        f'<div style="font-size:28px;font-weight:700;color:{num_col};line-height:1;">{count}</div>'
        f'<div style="font-size:11px;margin-top:3px;">{delta_cell}</div>'
        f'{spark}'
        f'</td>'
        f'<td width="48%" valign="middle" '
        f'style="padding:10px 12px 10px 8px;border-left:1px solid #F0F4FA;">'
        f'{kw_rows}'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


# ── Main HTML builder ──────────────────────────────────────────────

def _build_html(digest: dict) -> str:
    date_range   = digest['date_range']
    prev_date    = digest.get('prev_date_range')
    total        = digest['total']
    total_delta  = digest.get('total_delta', 0)
    weekly_total = digest.get('weekly_total', 0)
    avg_rating   = digest.get('avg_rating', 0.0)
    prev_avg     = digest.get('prev_avg_rating')
    top_issues   = digest['top_issues']
    color_map    = digest.get('color_map', {})
    trend_data   = digest.get('trend_data', {})
    by_category  = digest.get('by_category', {})
    history      = digest.get('history', [])
    spikes       = digest.get('spikes', [])

    display = [(c,n,d,t,p) for c,n,d,t,p in top_issues if c not in EXCLUDE]
    top6    = display[:MAX_CARDS]
    hidden  = len(display) - len(top6)

    # Avg rating delta
    if prev_avg is not None and prev_avg > 0:
        rd    = round(avg_rating - prev_avg, 1)
        avg_d = (f'<span style="color:#CC0000;font-size:10px;">↑ {rd:+.1f}</span>' if rd > 0
                 else f'<span style="color:#007A45;font-size:10px;">↓ {rd:.1f}</span>' if rd < 0
                 else '<span style="color:rgba(255,255,255,.45);font-size:10px;">→</span>')
    else:
        avg_d = '<span style="color:rgba(255,255,255,.45);font-size:10px;">first run</span>'

    comp     = f'vs {prev_date}' if prev_date and prev_date != date_range else ''
    prev_wt  = history[-1].get('weekly_total', 0) if history else 0
    wt_delta = weekly_total - prev_wt

    # ── Trend chart via QuickChart ─────────────────────────────────
    chart_url = _trend_chart_url(digest)
    if chart_url:
        trend_section = (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-bottom:18px;">'
            f'<tr><td style="font-size:11px;font-weight:600;color:{BRAND_BLUE};'
            f'text-transform:uppercase;letter-spacing:.5px;'
            f'border-bottom:2px solid {BRAND_CORAL_LT};padding-bottom:6px;'
            f'margin-bottom:10px;">Issue trend — last {len(digest.get("history",[]))+1} weeks'
            f'</td></tr>'
            f'<tr><td style="padding-top:12px;">'
            f'<img src="{chart_url}" width="540" alt="Issue trend chart" '
            f'style="display:block;width:100%;max-width:540px;border-radius:8px;'
            f'border:1px solid #EEF2F9;"/>'
            f'</td></tr></table>'
        )
    else:
        trend_section = (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-bottom:18px;">'
            f'<tr><td style="font-size:11px;color:#AAA;text-align:center;'
            f'padding:12px 0;font-style:italic;">'
            f'Trend chart will appear from week 2 onwards</td></tr></table>'
        )

    # ── Card grid ──────────────────────────────────────────────────
    cards_rows = ''
    i = 0
    while i < len(top6):
        cells = ''
        for j in range(3):
            idx = i + j
            if idx < len(top6):
                cat, count, delta, tag, prev = top6[idx]
                color   = color_map.get(cat, '#555')
                is_new  = any(c == cat and l == 'NEW' for c,n,l in spikes)
                series  = trend_data.get(cat, [])
                sp_cnts = [pt.get('count', 0) for pt in series]
                subs    = by_category.get(cat, {}).get('sub_categories', {})
                kws     = sorted(subs, key=lambda x: -subs[x])[:2]
                card    = _issue_card(cat, count, delta, color,
                                      is_new, sp_cnts, kws)
                cells  += f'<td width="31%" valign="top">{card}</td>'
                if j < 2:
                    cells += '<td width="3%"></td>'
            else:
                cells += (f'<td width="3%"></td>'
                          f'<td width="31%"></td>' if j == 1
                          else f'<td width="31%"></td>')
        cards_rows += (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-bottom:10px;"><tr>{cells}</tr></table>'
        )
        i += 3

    more_note = ''
    if hidden > 0:
        more_note = (
            f'<p style="font-size:11px;color:#AAA;text-align:center;margin:4px 0 14px;">'
            f'+ {hidden} more issue areas in full breakdown below</p>'
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#EEF2F7;
             font-family:'Helvetica Neue',Arial,sans-serif;color:#1A1A2E;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:20px 12px;">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:12px;overflow:hidden;
              box-shadow:0 2px 16px rgba(27,58,107,.10);">

  <!-- HEADER -->
  <tr><td style="background:{BRAND_CORAL};padding:18px 24px;">
    <div style="font-size:11px;color:rgba(255,255,255,.8);font-weight:600;
                letter-spacing:1.2px;margin-bottom:2px;">STASHFIN</div>
    <div style="font-size:17px;font-weight:600;color:#fff;">
      Play Store — Weekly Review Signal</div>
    <div style="font-size:11px;color:rgba(255,255,255,.7);margin-top:3px;">
      {date_range}{f' &nbsp;|&nbsp; {comp}' if comp else ''}</div>
  </td></tr>

  <!-- KPI STRIP -->
  <tr><td style="background:{BRAND_BLUE};padding:0;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="34%" align="center"
          style="padding:14px 8px;border-right:1px solid rgba(255,255,255,.12);">
        <div style="font-size:26px;font-weight:700;color:#fff;line-height:1;">
          {weekly_total or '—'}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;
                    text-transform:uppercase;letter-spacing:.6px;">Total reviews</div>
        <div style="font-size:10px;color:rgba(255,255,255,.5);margin-top:3px;">
          {_delta_html(wt_delta)}</div>
      </td>
      <td width="33%" align="center"
          style="padding:14px 8px;border-right:1px solid rgba(255,255,255,.12);">
        <div style="font-size:26px;font-weight:700;color:#FF7070;line-height:1;">{total}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;
                    text-transform:uppercase;letter-spacing:.6px;">1-2-3★ reviews</div>
        <div style="font-size:10px;margin-top:3px;">{_delta_html(total_delta)}</div>
      </td>
      <td width="33%" align="center" style="padding:14px 8px;">
        <div style="font-size:26px;font-weight:700;color:#90BFEE;line-height:1;">
          {avg_rating}{'★' if avg_rating else ''}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;
                    text-transform:uppercase;letter-spacing:.6px;">Avg rating</div>
        <div style="margin-top:3px;">{avg_d}</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- BODY -->
  <tr><td style="padding:18px 18px 20px;">

    {trend_section}

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">
      <tr><td style="font-size:11px;font-weight:600;color:{BRAND_BLUE};
                     text-transform:uppercase;letter-spacing:.6px;
                     border-bottom:2px solid {BRAND_CORAL_LT};padding-bottom:6px;">
        Issue breakdown
      </td></tr>
    </table>

    {cards_rows}
    {more_note}

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;">
      <tr><td align="center">
        <a href="{PAGES_URL}"
           style="display:inline-block;background:{BRAND_CORAL};color:#fff;
                  font-size:12px;font-weight:600;padding:11px 28px;
                  border-radius:6px;text-decoration:none;letter-spacing:.3px;">
          View full breakdown &amp; examples →
        </a>
      </td></tr>
    </table>

  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:{BRAND_BLUE_LT};padding:12px 24px;
                  border-top:1px solid #E0E8F4;">
    <div style="font-size:10px;color:#999;line-height:1.7;">
      <strong style="color:{BRAND_BLUE};">Note:</strong>
      Reviews reflect user perception — signals for discussion, not confirmed failures.<br>
      Auto-generated · {date_range} · 1-2-3★ only · Contact Vishal (Marketing)
    </div>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""
    return html


def publish_via_email(digest: dict) -> None:
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        log.warning('Gmail not configured')
        return
    if not EMAIL_ALL:
        log.warning('EMAIL_ALL empty')
        return

    html    = _build_html(digest)
    subject = f'stashfin Reviews | {digest["date_range"]} | {digest["total"]} signals'

    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = GMAIL_SENDER
    msg['To']      = ', '.join(EMAIL_ALL)
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_SENDER, EMAIL_ALL, msg.as_string())
        log.info(f'Email sent to {EMAIL_ALL}')
    except Exception as e:
        log.error(f'Email failed: {e}')
        raise
