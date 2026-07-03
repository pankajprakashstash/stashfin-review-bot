"""
email_publisher.py — Executive email in StashFin brand colors.

Fixes in this version:
- Trend chart: Gmail-safe HTML table bar comparison (SVG stripped by Gmail)
- Sparklines: table-based vertical bars (flexbox unreliable in Gmail)
- Cards: keywords shown from sub_categories, compact size
- No spike ribbon
- Simplified subject line
"""
from __future__ import annotations
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bot.config import (GMAIL_SENDER, GMAIL_APP_PASSWORD, EMAIL_ALL,
                        PAGES_URL, BRAND_CORAL, BRAND_BLUE,
                        BRAND_CORAL_LT, BRAND_BLUE_LT, ISSUE_COLORS)

log = logging.getLogger(__name__)
EXCLUDE = {'Uncategorized / No Text', 'Irrelevant / Gibberish', 'Positive Feedback'}


def _delta_html(n: int) -> str:
    if n > 0:  return f'<span style="color:#CC0000;font-weight:700">↑ +{n}</span>'
    if n < 0:  return f'<span style="color:#007A45;font-weight:700">↓ {n}</span>'
    return '<span style="color:#888;font-weight:600">→</span>'


def _lighten(hex_color: str, steps: int) -> str:
    """Return a lighter shade by mixing with white."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2],16), int(hex_color[2:4],16), int(hex_color[4:6],16)
    alpha = max(0.15, 1.0 - steps * 0.18)
    r2 = int(r + (255-r)*(1-alpha))
    g2 = int(g + (255-g)*(1-alpha))
    b2 = int(b + (255-b)*(1-alpha))
    return f'#{r2:02x}{g2:02x}{b2:02x}'


# ── Gmail-safe sparkline using table (not flexbox) ─────────────────

def _sparkline(counts: list[int], color: str) -> str:
    """
    Gmail-safe sparkline using a table with bottom-aligned cells.
    Each bar is a div inside a bottom-aligned td.
    """
    if not counts:
        return ''
    max_c  = max(counts) or 1
    max_h  = 18
    n      = len(counts)
    bars   = ''

    for i, c in enumerate(counts):
        h       = max(2, int((c / max_c) * max_h))
        # shade: oldest = lightest, newest = full color
        steps   = max(0, n - 1 - i)
        bg      = _lighten(color, steps) if steps > 0 else color
        bars   += (f'<td style="vertical-align:bottom;padding:0 1px 0 0;">'
                   f'<div style="width:7px;height:{h}px;background:{bg};'
                   f'font-size:0;line-height:0;">&nbsp;</div></td>')

    return (f'<table cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;margin-top:6px;">'
            f'<tr style="vertical-align:bottom;">{bars}</tr>'
            f'</table>')


# ── Keywords from sub-categories ───────────────────────────────────

def _keywords(data: dict) -> str:
    """Show top 2 sub-category keywords to fill card space."""
    subs = data.get('sub_categories', {})
    if not subs:
        return ''
    top = sorted(subs.items(), key=lambda x: -x[1])[:2]
    items = ''
    for sub, n in top:
        label  = sub[:32] + ('…' if len(sub) > 32 else '')
        items += (f'<div style="font-size:9px;color:#666;margin-top:3px;'
                  f'overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">'
                  f'• {label}</div>')
    return items


# ── Gmail-safe trend bars (replaces SVG which Gmail strips) ────────

def _trend_bars(digest: dict) -> str:
    """
    Gmail-safe horizontal bar comparison: this week vs last week.
    Each issue gets two rows of bars — thick coral for this week,
    thin light for last week. No SVG, no JavaScript.
    """
    history    = digest.get('history', [])
    top_issues = [(c,n,d,t,p) for c,n,d,t,p in digest['top_issues']
                  if c not in EXCLUDE][:6]
    color_map  = digest.get('color_map', {})

    if not top_issues:
        return ''

    has_history = bool(history)
    max_count   = max(n for _,n,*_ in top_issues) or 1
    MAX_W       = 150   # max bar width in px

    rows = ''
    for cat, count, delta, tag, prev in top_issues:
        color    = color_map.get(cat, BRAND_CORAL)
        this_w   = max(4, int((count / max_count) * MAX_W))
        prev_w   = max(0, int((prev  / max_count) * MAX_W)) if prev else 0
        short    = cat[:24] + ('…' if len(cat) > 24 else '')
        lt_color = _lighten(color, 3)

        this_bar = (f'<td style="vertical-align:middle;padding-bottom:2px;">'
                    f'<table cellpadding="0" cellspacing="0" border="0">'
                    f'<tr>'
                    f'<td style="vertical-align:middle;">'
                    f'<div style="width:{this_w}px;height:8px;background:{color};'
                    f'border-radius:2px;font-size:0;">&nbsp;</div></td>'
                    f'<td style="vertical-align:middle;padding-left:6px;'
                    f'font-size:12px;font-weight:700;color:{color};white-space:nowrap;">'
                    f'{count} &nbsp;{_delta_html(delta)}</td>'
                    f'</tr></table></td>')

        prev_bar = ''
        if has_history and prev > 0:
            prev_bar = (f'<td style="vertical-align:middle;">'
                        f'<table cellpadding="0" cellspacing="0" border="0">'
                        f'<tr>'
                        f'<td style="vertical-align:middle;">'
                        f'<div style="width:{prev_w}px;height:5px;background:{lt_color};'
                        f'border-radius:2px;font-size:0;">&nbsp;</div></td>'
                        f'<td style="vertical-align:middle;padding-left:6px;'
                        f'font-size:10px;color:#AAA;">{prev} prev</td>'
                        f'</tr></table></td>')
        elif has_history:
            prev_bar = f'<td style="font-size:10px;color:#CCC;padding-left:4px;">—</td>'

        rows += (f'<tr>'
                 f'<td style="padding:5px 8px 5px 0;font-size:11px;font-weight:600;'
                 f'color:{BRAND_BLUE};width:140px;vertical-align:middle;">{short}</td>'
                 f'{this_bar}'
                 f'{"" if not has_history else prev_bar}'
                 f'</tr>')

    legend = ''
    if has_history:
        legend = (f'<tr><td colspan="3" style="padding-top:10px;border-top:1px solid #F5F5F5;">'
                  f'<table cellpadding="0" cellspacing="0"><tr>'
                  f'<td style="padding-right:16px;">'
                  f'<table cellpadding="0" cellspacing="0"><tr>'
                  f'<td><div style="width:14px;height:6px;background:{BRAND_CORAL};'
                  f'border-radius:2px;">&nbsp;</div></td>'
                  f'<td style="font-size:9px;color:#AAA;padding-left:4px;">This week</td>'
                  f'</tr></table></td>'
                  f'<td>'
                  f'<table cellpadding="0" cellspacing="0"><tr>'
                  f'<td><div style="width:14px;height:4px;background:#FFB3B3;'
                  f'border-radius:2px;">&nbsp;</div></td>'
                  f'<td style="font-size:9px;color:#AAA;padding-left:4px;">Last week</td>'
                  f'</tr></table></td>'
                  f'</tr></table></td></tr>')

    return (f'<div style="background:#FAFBFD;border:1px solid #EEF2F9;'
            f'border-radius:8px;padding:12px 14px;margin-bottom:18px;">'
            f'<div style="font-size:10px;font-weight:600;color:{BRAND_BLUE};'
            f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;">'
            f'{"Issue volume — this week vs last week" if has_history else "Issue volume this week"}'
            f'</div>'
            f'<table cellpadding="0" cellspacing="0" border="0" width="100%">'
            f'{rows}{legend}</table></div>')


# ── Issue card ─────────────────────────────────────────────────────

def _issue_card(cat: str, count: int, delta: int, prev: int,
                color: str, spark_counts: list[int],
                is_new: bool, data: dict) -> str:
    short    = cat[:20] + ('…' if len(cat) > 20 else '')
    hdr_col  = '#00875A' if is_new else color
    num_col  = '#00875A' if is_new else color
    spark    = _sparkline(spark_counts, color)
    keywords = _keywords(data)

    if is_new:
        delta_html = ('<span style="background:#00875A;color:#fff;font-size:9px;'
                      'padding:1px 6px;border-radius:3px;font-weight:700;">NEW</span>')
    else:
        delta_html = _delta_html(delta)

    return (f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border:1.5px solid {hdr_col};border-radius:8px;'
            f'overflow:hidden;background:#fff;">'
            f'<tr><td style="background:{hdr_col};padding:6px 10px;">'
            f'<span style="color:#fff;font-size:10px;font-weight:600;">{short}</span>'
            f'</td></tr>'
            f'<tr><td style="padding:8px 10px 8px;">'
            f'<div style="font-size:22px;font-weight:700;color:{num_col};'
            f'line-height:1;text-align:center;">{count}</div>'
            f'<div style="font-size:11px;margin-top:2px;text-align:center;">{delta_html}</div>'
            f'{spark}'
            f'{keywords}'
            f'</td></tr>'
            f'</table>')


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
    history      = digest.get('history', [])
    spikes       = digest.get('spikes', [])

    display = [(c,n,d,t,p) for c,n,d,t,p in top_issues if c not in EXCLUDE]

    # Avg rating delta
    if prev_avg is not None:
        rd = round(avg_rating - prev_avg, 1)
        avg_d = (f'<span style="color:#CC0000;font-size:10px;">↑ {rd:+.1f}</span>' if rd > 0
                 else f'<span style="color:#007A45;font-size:10px;">↓ {rd:.1f}</span>' if rd < 0
                 else '<span style="color:rgba(255,255,255,.45);font-size:10px;">→</span>')
    else:
        avg_d = '<span style="color:rgba(255,255,255,.45);font-size:10px;">first run</span>'

    comp = f'vs week of {prev_date}' if prev_date else ''

    prev_wt  = history[-1].get('weekly_total', 0) if history else 0
    wt_delta = weekly_total - prev_wt

    # Trend bars (Gmail-safe)
    trend_section = _trend_bars(digest)

    # Cards — 3 per row
    cards_rows = ''
    i = 0
    while i < len(display):
        row_cells = ''
        for j in range(3):
            if i + j < len(display):
                cat, count, delta, tag, prev = display[i+j]
                color       = color_map.get(cat, '#555')
                is_new      = any(c==cat and l=='NEW' for c,n,l in spikes)
                series      = trend_data.get(cat, [])
                sp_counts   = [pt.get('count',0) for pt in series]
                card_data   = digest['by_category'].get(cat, {})
                card_html   = _issue_card(cat, count, delta, prev,
                                          color, sp_counts, is_new, card_data)
                row_cells  += f'<td width="31%" valign="top">{card_html}</td>'
                if j < 2 and i+j+1 < len(display):
                    row_cells += '<td width="3%"></td>'
            else:
                if j < 2 and i+j < len(display)-1:
                    row_cells += '<td width="3%"></td>'
                row_cells += '<td width="31%"></td>'

        cards_rows += (f'<table width="100%" cellpadding="0" cellspacing="0" '
                       f'style="margin-bottom:10px;"><tr>{row_cells}</tr></table>')
        i += 3

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#EEF2F7;
             font-family:'Helvetica Neue',Arial,sans-serif;color:#1A1A2E;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:20px 12px;">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:12px;overflow:hidden;
              box-shadow:0 2px 16px rgba(27,58,107,.12);">

  <tr><td style="background:{BRAND_CORAL};padding:18px 24px;">
    <div style="font-size:11px;color:rgba(255,255,255,.8);font-weight:600;
                letter-spacing:1.2px;margin-bottom:2px;">STASHFIN</div>
    <div style="font-size:17px;font-weight:600;color:#fff;">
      Play Store — Weekly Review Signal</div>
    <div style="font-size:11px;color:rgba(255,255,255,.7);margin-top:3px;">
      {date_range}{f' &nbsp;|&nbsp; {comp}' if comp else ''}</div>
  </td></tr>

  <tr><td style="background:{BRAND_BLUE};padding:0;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="34%" align="center"
          style="padding:14px 8px;border-right:1px solid rgba(255,255,255,.1);">
        <div style="font-size:26px;font-weight:700;color:#fff;line-height:1;">
          {weekly_total or '—'}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;
                    text-transform:uppercase;letter-spacing:.5px;">Total reviews</div>
        <div style="font-size:10px;margin-top:2px;">{_delta_html(wt_delta)}</div>
      </td>
      <td width="33%" align="center"
          style="padding:14px 8px;border-right:1px solid rgba(255,255,255,.1);">
        <div style="font-size:26px;font-weight:700;color:#FF7070;line-height:1;">{total}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;
                    text-transform:uppercase;letter-spacing:.5px;">1-2-3★ reviews</div>
        <div style="font-size:10px;margin-top:2px;">{_delta_html(total_delta)}</div>
      </td>
      <td width="33%" align="center" style="padding:14px 8px;">
        <div style="font-size:26px;font-weight:700;color:#90BFEE;line-height:1;">
          {avg_rating}{'★' if avg_rating else ''}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;
                    text-transform:uppercase;letter-spacing:.5px;">Avg rating</div>
        <div style="margin-top:2px;">{avg_d}</div>
      </td>
    </tr></table>
  </td></tr>

  <tr><td style="padding:18px 18px 20px;">

    {trend_section}

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">
      <tr><td style="font-size:11px;font-weight:600;color:{BRAND_BLUE};
                     text-transform:uppercase;letter-spacing:.5px;
                     border-bottom:2px solid {BRAND_CORAL_LT};padding-bottom:6px;">
        Issue breakdown
      </td></tr>
    </table>

    {cards_rows}

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;">
      <tr><td align="center">
        <a href="{PAGES_URL}"
           style="display:inline-block;background:{BRAND_CORAL};color:#fff;
                  font-size:12px;font-weight:600;padding:11px 28px;border-radius:6px;
                  text-decoration:none;letter-spacing:.3px;">
          View full breakdown &amp; examples →
        </a>
      </td></tr>
    </table>

  </td></tr>

  <tr><td style="background:{BRAND_BLUE_LT};padding:12px 24px;
                  border-top:1px solid #E0E8F4;">
    <div style="font-size:10px;color:#999;line-height:1.7;">
      <strong style="color:{BRAND_BLUE};">Note:</strong>
      Reviews reflect user perception — signals for discussion, not confirmed failures.
      Each area should be investigated before conclusions are drawn.<br>
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
