"""
email_publisher.py — Executive email, all fixes applied.
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

log       = logging.getLogger(__name__)
EXCLUDE   = {'Uncategorized / No Text', 'Irrelevant / Gibberish', 'Positive Feedback'}
MAX_CARDS = 6


def _lighten(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    r2 = int(r + (255-r)*factor)
    g2 = int(g + (255-g)*factor)
    b2 = int(b + (255-b)*factor)
    return f'#{r2:02x}{g2:02x}{b2:02x}'


def _delta_html(n: int, size: str = '11px') -> str:
    if n > 0:
        return f'<span style="color:#CC0000;font-weight:700;font-size:{size};">↑ +{n}</span>'
    if n < 0:
        return f'<span style="color:#007A45;font-weight:700;font-size:{size};">↓ {n}</span>'
    return f'<span style="color:#999;font-size:{size};">→</span>'


def _trend_chart_url(digest: dict) -> str:
    """
    QuickChart.io URL for smooth trend line chart.
    v=4 forces Chart.js 4 which supports cubicInterpolationMode.
    cnt_by_date alignment matches detail page logic exactly.
    """
    history    = digest.get('history', [])
    top_issues = [(c,n,d,t,p) for c,n,d,t,p in digest['top_issues']
                  if c not in EXCLUDE][:5]
    trend_data = digest.get('trend_data', {})
    color_map  = digest.get('color_map', {})

    if not top_issues:
        return ''

    first_series    = trend_data.get(top_issues[0][0], [])
    week_labels     = []   # short labels for X axis display
    week_labels_raw = []   # full date range strings for data lookup

    for pt in first_series:
        dr    = pt.get('date', '')
        short = dr.split('–')[0].strip() if '–' in dr else dr[:8]
        week_labels.append(short)
        week_labels_raw.append(dr)

    if len(week_labels) < 2:
        return ''

    datasets = []
    for cat, *_ in top_issues:
        color       = color_map.get(cat, BRAND_CORAL)
        series      = trend_data.get(cat, [])
        cnt_by_date = {pt.get('date', ''): pt.get('count', 0) for pt in series}
        values      = [cnt_by_date.get(wk, 0) for wk in week_labels_raw]
        if len(values) != len(week_labels):
            continue
        label = cat[:18] + ('…' if len(cat) > 18 else '')
        datasets.append({
            'label':                  label,
            'data':                   values,
            'borderColor':            color,
            'backgroundColor':        color + '18',
            'fill':                   False,
            'tension':                0.4,
            'cubicInterpolationMode': 'monotone',
            'pointRadius':            4,
            'pointHoverRadius':       6,
            'borderWidth':            2.5,
        })

    if not datasets:
        return ''

    chart_config = {
        'type': 'line',
        'data': {'labels': week_labels, 'datasets': datasets},
        'options': {
            'scales': {
                'y': {
                    'beginAtZero': True,
                    'grid': {'color': '#F0F0F0'},
                    'ticks': {'font': {'size': 11}},
                },
                'x': {
                    'grid': {'color': '#F5F5F5'},
                    'ticks': {'font': {'size': 10}},
                },
            },
            'plugins': {
                'legend': {
                    'position': 'bottom',
                    'labels': {'font': {'size': 10}, 'boxWidth': 12, 'padding': 12},
                },
            },
        },
    }

    config_str = json.dumps(chart_config, separators=(',', ':'))
    encoded    = urllib.parse.quote(config_str, safe='')
    return f'https://quickchart.io/chart?w=540&h=200&bkg=white&v=4&c={encoded}'


def _sparkline_with_delta(counts: list[int], color: str, delta: int) -> str:
    if not counts:
        return ''

    max_c = max(counts) or 1
    MAX_H = 20
    n     = len(counts)

    delta_cells = ''
    for i in range(n):
        if i == n - 1:
            if delta > 0:
                d = f'<span style="color:#CC0000;font-size:8px;font-weight:700;">↑+{delta}</span>'
            elif delta < 0:
                d = f'<span style="color:#007A45;font-size:8px;font-weight:700;">↓{delta}</span>'
            else:
                d = f'<span style="color:#999;font-size:8px;">→</span>'
            delta_cells += (f'<td style="text-align:center;padding:0 1px 1px 0;'
                            f'white-space:nowrap;">{d}</td>')
        else:
            delta_cells += '<td style="padding:0 1px 0 0;"></td>'

    bar_cells = ''
    for i, c in enumerate(counts):
        bar_h  = max(2, int((c / max_c) * MAX_H))
        gap_h  = MAX_H - bar_h
        factor = max(0.0, (n - 1 - i) * 0.17)
        bg     = _lighten(color, factor)
        bar_cells += (
            f'<td style="vertical-align:bottom;padding:0 1px 0 0;">'
            f'<table cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td style="height:{gap_h}px;width:7px;font-size:0;">&nbsp;</td></tr>'
            f'<tr><td style="height:{bar_h}px;width:7px;background:{bg};'
            f'font-size:0;line-height:0;">&nbsp;</td></tr>'
            f'</table></td>'
        )

    return (
        f'<table cellpadding="0" cellspacing="0" border="0" style="margin-top:6px;">'
        f'<tr>{delta_cells}</tr>'
        f'<tr style="vertical-align:bottom;">{bar_cells}</tr>'
        f'</table>'
    )


def _issue_card(cat: str, count: int, delta: int,
                color: str, is_new: bool,
                spark_counts: list[int], keywords: list[str]) -> str:

    short   = cat[:22] + ('…' if len(cat) > 22 else '')
    hdr_col = '#007A45' if is_new else color
    num_col = '#007A45' if is_new else color

    if is_new:
        count_display = (
            f'<div style="font-size:26px;font-weight:700;color:{num_col};line-height:1;">{count}</div>'
            f'<div style="margin-top:3px;">'
            f'<span style="background:#007A45;color:#fff;font-size:9px;'
            f'padding:2px 7px;border-radius:3px;font-weight:700;">NEW</span>'
            f'</div>'
        )
    else:
        count_display = (
            f'<div style="font-size:26px;font-weight:700;color:{num_col};line-height:1;">{count}</div>'
        )

    spark = _sparkline_with_delta(spark_counts, color, delta)

    kw_rows = ''.join(
        f'<div style="font-size:10px;color:#444;padding:3px 0;line-height:1.4;">'
        f'• {kw[:26]}{"…" if len(kw)>26 else ""}</div>'
        for kw in keywords[:2]
    ) or '<div style="font-size:10px;color:#CCC;">—</div>'

    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border:1.5px solid {hdr_col};border-radius:8px;'
        f'overflow:hidden;background:#fff;">'
        f'<tr><td colspan="2" '
        f'style="background:{hdr_col};padding:0 12px;height:34px;'
        f'border-radius:6px 6px 0 0;vertical-align:middle;">'
        f'<span style="color:#fff;font-size:10px;font-weight:600;'
        f'letter-spacing:0.2px;line-height:1.3;">{short}</span>'
        f'</td></tr>'
        f'<tr>'
        f'<td width="52%" valign="top" style="padding:10px 8px 10px 12px;">'
        f'{count_display}'
        f'{spark}'
        f'</td>'
        f'<td width="48%" valign="middle" '
        f'style="padding:10px 12px 10px 8px;border-left:1px solid #F0F4FA;">'
        f'{kw_rows}'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


def _build_html(digest: dict) -> str:
    date_range   = digest['date_range']
    prev_date    = digest.get('prev_date_range')
    total        = digest['total']
    total_delta  = digest.get('total_delta', 0)
    top_issues   = digest['top_issues']
    color_map    = digest.get('color_map', {})
    trend_data   = digest.get('trend_data', {})
    by_category  = digest.get('by_category', {})
    history      = digest.get('history', [])
    spikes       = digest.get('spikes', [])
    star_counts  = digest.get('star_counts', {})

    display = [(c,n,d,t,p) for c,n,d,t,p in top_issues if c not in EXCLUDE]
    top6    = display[:MAX_CARDS]
    hidden  = len(display) - len(top6)

    comp = f'vs {prev_date}' if prev_date and prev_date != date_range else ''

    # Trend chart
    chart_url = _trend_chart_url(digest)
    if chart_url:
        trend_section = (
            f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:18px;">'
            f'<tr><td style="font-size:11px;font-weight:600;color:{BRAND_BLUE};'
            f'text-transform:uppercase;letter-spacing:.5px;'
            f'border-bottom:2px solid {BRAND_CORAL_LT};padding-bottom:6px;">'
            f'Issue trend — last {len(digest.get("history",[]))+1} weeks'
            f'</td></tr>'
            f'<tr><td style="padding-top:12px;">'
            f'<img src="{chart_url}" width="540" alt="Issue trend chart" '
            f'style="display:block;width:100%;max-width:540px;border-radius:8px;'
            f'border:1px solid #EEF2F9;"/>'
            f'</td></tr></table>'
        )
    else:
        trend_section = (
            f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:18px;">'
            f'<tr><td style="font-size:11px;color:#AAA;text-align:center;'
            f'padding:12px 0;font-style:italic;">'
            f'Trend chart appears from week 2 onwards</td></tr></table>'
        )

    # Cards 3 per row
    cards_rows = ''
    i = 0
    while i < len(top6):
        cells = ''
        for j in range(3):
            idx = i + j
            if idx < len(top6):
                cat, count, delta, tag, prev = top6[idx]
                color   = color_map.get(cat, BRAND_CORAL)
                is_new  = any(c == cat and l == 'NEW' for c,n,l in spikes)
                series  = trend_data.get(cat, [])
                sp_cnts = [pt.get('count', 0) for pt in series]
                subs    = by_category.get(cat, {}).get('sub_categories', {})
                kws     = sorted(subs, key=lambda x: -subs[x])[:2]
                card    = _issue_card(cat, count, delta, color,
                                      is_new, sp_cnts, kws)
                cells  += f'<td width="31%" valign="top">{card}</td>'
            else:
                cells  += f'<td width="31%"></td>'
            if j < 2:
                cells += '<td width="3%"></td>'

        cards_rows += (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin-bottom:10px;"><tr>{cells}</tr></table>'
        )
        i += 3

    more_note = ''
    if hidden > 0:
        more_note = (
            f'<p style="font-size:11px;color:#AAA;text-align:center;margin:2px 0 12px;">'
            f'+ {hidden} more areas in full breakdown</p>'
        )

    # KPI strip
    kpi_html = (
        f'<tr><td style="background:{BRAND_BLUE};padding:0;">'
        f'<table width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td width="50%" align="center" '
        f'style="padding:16px 8px;border-right:1px solid rgba(255,255,255,.12);">'
        f'<div style="font-size:34px;font-weight:700;color:#FF7070;line-height:1;">{total}</div>'
        f'<div style="font-size:9px;color:rgba(255,255,255,.6);margin-top:3px;'
        f'text-transform:uppercase;letter-spacing:.6px;">1-2-3★ reviews</div>'
        f'<div style="font-size:10px;margin-top:4px;">{_delta_html(total_delta)}</div>'
        f'</td>'
        f'<td width="50%" align="center" style="padding:16px 8px;">'
        f'<div style="display:inline-block;text-align:left;">'
        f'<div style="font-size:11px;color:rgba(255,255,255,.75);'
        f'line-height:2;white-space:nowrap;">'
        f'1★ &nbsp;<strong style="color:#FF7070;font-size:14px;">'
        f'{star_counts.get(1, 0)}</strong></div>'
        f'<div style="font-size:11px;color:rgba(255,255,255,.75);'
        f'line-height:2;white-space:nowrap;">'
        f'2★ &nbsp;<strong style="color:#FF9090;font-size:14px;">'
        f'{star_counts.get(2, 0)}</strong></div>'
        f'<div style="font-size:11px;color:rgba(255,255,255,.75);'
        f'line-height:2;white-space:nowrap;">'
        f'3★ &nbsp;<strong style="color:#FFB3B3;font-size:14px;">'
        f'{star_counts.get(3, 0)}</strong></div>'
        f'</div>'
        f'</td>'
        f'</tr></table></td></tr>'
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

  <tr><td style="background:{BRAND_CORAL};padding:18px 24px;">
    <div style="font-size:11px;color:rgba(255,255,255,.8);font-weight:600;
                letter-spacing:1.2px;margin-bottom:2px;">STASHFIN</div>
    <div style="font-size:17px;font-weight:600;color:#fff;">
      Play Store — Weekly Review Signal</div>
    <div style="font-size:11px;color:rgba(255,255,255,.7);margin-top:3px;">
      {date_range}{f' &nbsp;|&nbsp; {comp}' if comp else ''}</div>
  </td></tr>

  {kpi_html}

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
