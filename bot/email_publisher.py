"""
email_publisher.py — Executive email in StashFin brand colors.

Layout:
  1. Header — coral red, stashfin branding
  2. KPI strip — dark blue, 3 tiles: total reviews, 1-2-3★, avg rating
  3. SVG trend chart — 6-week lines per issue, color-matched to cards
  4. Issue cards — 3 per row, color-matched, sparklines, delta arrows
  5. CTA button — "View full breakdown"
  6. Footer disclaimer

Rules:
  - No yellow anywhere
  - Red (↑) for rising, green (↓) for declining
  - NEW label in green
  - No sentiment section
  - No text heavy descriptions — numbers + keywords only in email
  - SVG chart works in Gmail (Google Workspace). Uses inline SVG.
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

EXCLUDE      = {'Uncategorized / No Text', 'Irrelevant / Gibberish', 'Positive Feedback'}


# ── Helpers ────────────────────────────────────────────────────────

def _delta_html(n: int) -> str:
    if n > 0:  return f'<span style="color:#CC0000;font-weight:700">↑ +{n}</span>'
    if n < 0:  return f'<span style="color:#007A45;font-weight:700">↓ {n}</span>'
    return '<span style="color:#888;font-weight:600">→</span>'


def _lighten(hex_color: str, alpha: float) -> str:
    """Simulate lightening by returning rgba string."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2],16), int(hex_color[2:4],16), int(hex_color[4:6],16)
    # Mix with white
    r2 = int(r + (255-r)*(1-alpha))
    g2 = int(g + (255-g)*(1-alpha))
    b2 = int(b + (255-b)*(1-alpha))
    return f'#{r2:02x}{g2:02x}{b2:02x}'


# ── SVG Trend Chart ────────────────────────────────────────────────

def _trend_svg(digest: dict) -> str:
    history    = digest.get('history', [])
    color_map  = digest.get('color_map', {})
    top_issues = [(c,n,d,t,p) for c,n,d,t,p in digest['top_issues']
                  if c not in EXCLUDE][:5]
    trend_data = digest.get('trend_data', {})

    if not top_issues:
        return ''

    # Build unified week list
    all_weeks = [wk.get('date_range','') for wk in history[-5:]] + [digest['date_range']]
    n_weeks   = len(all_weeks)
    if n_weeks < 2:
        return '<div style="text-align:center;font-size:11px;color:#AAA;padding:12px 0;">Trend chart will appear from week 2 onwards</div>'

    # SVG layout
    W, H       = 520, 110
    LEFT, RIGHT = 8, 510
    TOP, BOTTOM = 8, 96
    chart_w    = RIGHT - LEFT
    chart_h    = BOTTOM - TOP

    # Find max count for scaling
    max_c = 1
    for cat, *_ in top_issues:
        for pt in trend_data.get(cat, []):
            max_c = max(max_c, pt.get('count', 0))

    def x_pos(i):
        return LEFT + (i / (n_weeks-1)) * chart_w

    def y_pos(count):
        return BOTTOM - (count / max_c) * chart_h

    # Grid lines
    grid = ''
    for frac in [0.25, 0.5, 0.75, 1.0]:
        y = y_pos(max_c * frac)
        val = int(max_c * frac)
        grid += f'<line x1="{LEFT}" y1="{y:.1f}" x2="{RIGHT}" y2="{y:.1f}" stroke="#F0F0F0" stroke-width="0.5"/>'
        grid += f'<text x="{LEFT-2}" y="{y+3:.1f}" font-size="7" fill="#CCC" text-anchor="end">{val}</text>'

    # X labels
    x_labels = ''
    for i, wk_label in enumerate(all_weeks):
        x   = x_pos(i)
        short = wk_label[:6] if wk_label else ''
        col = BRAND_CORAL if i == len(all_weeks)-1 else '#CCC'
        fw  = 'font-weight="600"' if i == len(all_weeks)-1 else ''
        x_labels += f'<text x="{x:.1f}" y="{H}" font-size="8" fill="{col}" text-anchor="middle" {fw}>{short}</text>'

    # "This week" shade
    if n_weeks > 1:
        last_x = x_pos(n_weeks-1)
        prev_x = x_pos(n_weeks-2)
        shade_x = (last_x + prev_x) / 2
        shade_w = last_x - shade_x + 5
        shading = f'<rect x="{shade_x:.1f}" y="{TOP}" width="{shade_w:.1f}" height="{chart_h}" fill="{BRAND_CORAL}" opacity="0.04"/>'
    else:
        shading = ''

    # Lines and dots
    lines = ''
    legend_items = []
    for cat, count, delta, tag, prev in top_issues:
        color  = color_map.get(cat, '#888')
        series = trend_data.get(cat, [])
        # Align series to all_weeks
        count_by_date = {pt.get('date',''): pt.get('count',0) for pt in series}
        pts = []
        for i, wk in enumerate(all_weeks):
            c  = count_by_date.get(wk, 0)
            pts.append((x_pos(i), y_pos(c), c))

        pts_str = ' '.join(f'{x:.1f},{y:.1f}' for x,y,_ in pts)
        lines  += f'<polyline points="{pts_str}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        for i,(x,y,c) in enumerate(pts):
            r  = 4 if i==len(pts)-1 else 3
            sw = f' stroke="#fff" stroke-width="1.5"' if i==len(pts)-1 else ''
            lines += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}"{sw}/>'

        short_name = cat[:20] + ('…' if len(cat)>20 else '')
        legend_items.append(f'<div style="display:inline-flex;align-items:center;gap:4px;margin-right:12px;">'
                            f'<div style="width:14px;height:2.5px;background:{color};border-radius:2px;"></div>'
                            f'<span style="font-size:10px;color:#666;">{short_name}</span></div>')

    legend_html = f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid #F0F4F8;">{"".join(legend_items)}</div>'

    svg = (f'<svg width="100%" viewBox="0 0 {W} {H}" style="display:block;overflow:visible;">'
           f'{grid}{shading}{lines}{x_labels}</svg>')

    return (f'<div style="background:#FAFBFD;border:1px solid #EEF2F9;border-radius:8px;'
            f'padding:12px 14px;margin-bottom:18px;">'
            f'<div style="font-size:10px;font-weight:600;color:{BRAND_BLUE};'
            f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;">'
            f'Issue trend — last {n_weeks} weeks (shaded = this week)</div>'
            f'{svg}{legend_html}</div>')


# ── Sparkline ──────────────────────────────────────────────────────

def _sparkline(counts: list[int], color: str, new_this_week: bool = False) -> str:
    if not counts:
        return ''
    max_c = max(counts) or 1
    max_h = 18
    n     = len(counts)
    alphas = [0.18, 0.30, 0.45, 0.60, 0.75, 1.0]

    bars = ''
    for i, c in enumerate(counts):
        h       = max(1, int((c / max_c) * max_h))
        a_idx   = max(0, 6-n+i)
        alpha   = alphas[min(a_idx, len(alphas)-1)]
        bg      = _lighten(color, alpha) if alpha < 1 else color
        bars   += (f'<div style="width:7px;height:{h}px;background:{bg};'
                   f'border-radius:1px 1px 0 0;flex-shrink:0;"></div>')

    return (f'<div style="display:flex;align-items:flex-end;gap:2px;height:{max_h}px;'
            f'margin-top:6px;">{bars}</div>')


# ── Issue card ─────────────────────────────────────────────────────

def _issue_card(cat: str, count: int, delta: int, prev: int,
                color: str, sparkline_counts: list[int], is_new: bool) -> str:
    short = cat[:22] + ('…' if len(cat)>22 else '')
    hdr_color = '#00875A' if is_new else color
    spark = _sparkline(sparkline_counts, color, is_new)

    if is_new:
        delta_html = '<span style="background:#00875A;color:#fff;font-size:9px;padding:1px 6px;border-radius:3px;font-weight:700;">NEW</span>'
    else:
        delta_html = _delta_html(delta)

    num_color = color if not is_new else '#00875A'

    return (f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border:1.5px solid {hdr_color};border-radius:8px;overflow:hidden;background:#fff;">'
            f'<tr><td style="background:{hdr_color};padding:6px 10px;">'
            f'<span style="color:#fff;font-size:10px;font-weight:600;line-height:1.3;">{short}</span>'
            f'</td></tr>'
            f'<tr><td style="padding:8px 10px 8px;">'
            f'<div style="font-size:26px;font-weight:700;color:{num_color};line-height:1;">{count}</div>'
            f'<div style="font-size:11px;margin-top:2px;">{delta_html}</div>'
            f'{spark}'
            f'</td></tr>'
            f'</table>')


# ── Spike banner ───────────────────────────────────────────────────

def _spike_banner(spikes: list, color_map: dict) -> str:
    if not spikes:
        return ''
    items = ''.join(
        f'<span style="background:{color_map.get(cat, BRAND_CORAL)};color:#fff;'
        f'font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px;margin-right:6px;'
        f'white-space:nowrap;">{cat[:18]}: {count} {label}</span>'
        for cat, count, label in spikes[:4]
    )
    return (f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:18px;">'
            f'<tr><td style="background:{BRAND_CORAL_LT};border-left:4px solid {BRAND_CORAL};'
            f'padding:10px 14px;border-radius:0 6px 6px 0;">'
            f'<span style="font-size:11px;font-weight:600;color:{BRAND_BLUE};">⚠ This week: </span>'
            f'{items}</td></tr></table>')


# ── Main HTML builder ──────────────────────────────────────────────

def _build_html(digest: dict) -> str:
    date_range   = digest['date_range']
    prev_date    = digest.get('prev_date_range')
    total        = digest['total']
    total_delta  = digest.get('total_delta', 0)
    weekly_total = digest.get('weekly_total', 0)
    avg_rating   = digest.get('avg_rating', 0.0)
    prev_avg     = digest.get('prev_avg_rating')
    spikes       = digest.get('spikes', [])
    top_issues   = digest['top_issues']
    color_map    = digest.get('color_map', {})
    trend_data   = digest.get('trend_data', {})
    history      = digest.get('history', [])

    display = [(c,n,d,t,p) for c,n,d,t,p in top_issues if c not in EXCLUDE]

    # Avg rating delta
    if prev_avg is not None:
        rd = round(avg_rating - prev_avg, 1)
        avg_delta = (f'<span style="color:#CC0000;font-size:10px;">↑ {rd:+.1f}</span>' if rd > 0
                     else f'<span style="color:#007A45;font-size:10px;">↓ {rd:.1f}</span>' if rd < 0
                     else '<span style="color:#888;font-size:10px;">→</span>')
    else:
        avg_delta = '<span style="color:rgba(255,255,255,.45);font-size:10px;">first run</span>'

    # Comparison subtitle
    comp = f'vs week of {prev_date}' if prev_date else ''

    # Weekly total delta vs previous
    prev_wt = history[-1].get('weekly_total', 0) if history else 0
    wt_delta = weekly_total - prev_wt
    wt_delta_html = (_delta_html(wt_delta) if wt_delta != 0 else
                     '<span style="color:rgba(255,255,255,.45)">—</span>')

    # Trend SVG chart
    trend_section = _trend_svg(digest)

    # Spike banner
    spike_html = _spike_banner(spikes, color_map)

    # Issue cards — 3 per row
    cards_rows = ''
    i = 0
    while i < len(display):
        row_cells = ''
        for j in range(3):
            if i + j < len(display):
                cat, count, delta, tag, prev = display[i+j]
                color = color_map.get(cat, '#555')
                is_new = any(c==cat and l=='NEW' for c,n,l in spikes)
                # Build sparkline counts from trend_data
                series = trend_data.get(cat, [])
                sp_counts = [pt.get('count',0) for pt in series]
                card_html = _issue_card(cat, count, delta, prev, color, sp_counts, is_new)
                row_cells += f'<td width="31%" valign="top">{card_html}</td>'
                if j < 2 and i+j+1 < len(display):
                    row_cells += '<td width="3%"></td>'
            else:
                row_cells += '<td width="31%"></td>'
                if j < 2:
                    row_cells += '<td width="3%"></td>'

        cards_rows += f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;"><tr>{row_cells}</tr></table>'
        i += 3

    # Section title
    section_title = (f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">'
                     f'<tr><td style="font-size:11px;font-weight:600;color:{BRAND_BLUE};'
                     f'text-transform:uppercase;letter-spacing:.5px;'
                     f'border-bottom:2px solid {BRAND_CORAL_LT};padding-bottom:6px;">'
                     f'Issue breakdown</td></tr></table>')

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#EEF2F7;font-family:'Helvetica Neue',Arial,sans-serif;color:#1A1A2E;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:20px 12px;">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(27,58,107,.12);">

  <!-- HEADER -->
  <tr><td style="background:{BRAND_CORAL};padding:18px 24px;">
    <div style="font-size:11px;color:rgba(255,255,255,.8);font-weight:600;letter-spacing:1.2px;margin-bottom:2px;">STASHFIN</div>
    <div style="font-size:17px;font-weight:600;color:#fff;">Play Store — Weekly Review Signal</div>
    <div style="font-size:11px;color:rgba(255,255,255,.7);margin-top:3px;">{date_range}{f' &nbsp;|&nbsp; {comp}' if comp else ''}</div>
  </td></tr>

  <!-- KPI STRIP -->
  <tr><td style="background:{BRAND_BLUE};padding:0;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="34%" align="center" style="padding:14px 8px;border-right:1px solid rgba(255,255,255,.1);">
        <div style="font-size:28px;font-weight:700;color:#fff;line-height:1;">{weekly_total or '—'}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;text-transform:uppercase;letter-spacing:.5px;">Total reviews</div>
        <div style="font-size:10px;margin-top:2px;">{wt_delta_html}</div>
      </td>
      <td width="33%" align="center" style="padding:14px 8px;border-right:1px solid rgba(255,255,255,.1);">
        <div style="font-size:28px;font-weight:700;color:#FF7070;line-height:1;">{total}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;text-transform:uppercase;letter-spacing:.5px;">1-2-3★ reviews</div>
        <div style="font-size:10px;margin-top:2px;">{_delta_html(total_delta)}</div>
      </td>
      <td width="33%" align="center" style="padding:14px 8px;">
        <div style="font-size:28px;font-weight:700;color:#90BFEE;line-height:1;">{avg_rating}{'★' if avg_rating else ''}</div>
        <div style="font-size:9px;color:rgba(255,255,255,.55);margin-top:3px;text-transform:uppercase;letter-spacing:.5px;">Avg rating</div>
        <div style="font-size:10px;margin-top:2px;">{avg_delta}</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- BODY -->
  <tr><td style="padding:18px 18px 20px;">
    {spike_html}
    {trend_section}
    {section_title}
    {cards_rows}

    <!-- CTA -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;">
      <tr><td align="center">
        <a href="{PAGES_URL}"
           style="display:inline-block;background:{BRAND_CORAL};color:#fff;font-size:12px;
                  font-weight:600;padding:11px 28px;border-radius:6px;text-decoration:none;
                  letter-spacing:.3px;">
          View full breakdown &amp; examples →
        </a>
      </td></tr>
    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:{BRAND_BLUE_LT};padding:12px 24px;border-top:1px solid #E0E8F4;">
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


# ── Send ───────────────────────────────────────────────────────────

def publish_via_email(digest: dict) -> None:
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        log.warning('Gmail not configured')
        return
    if not EMAIL_ALL:
        log.warning('EMAIL_ALL empty — no recipients')
        return

    html      = _build_html(digest)
    top       = digest['top_issues']
    spikes    = digest.get('spikes', [])
    top_names = ' · '.join(c for c,*_ in top[:3]) if top else 'No issues'
    spike_flg = ' ⚠️' if spikes else ''
    subject   = (f'stashfin Reviews | {digest["date_range"]} | '
                 f'{digest["total"]} signals{spike_flg} | {top_names}')

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
