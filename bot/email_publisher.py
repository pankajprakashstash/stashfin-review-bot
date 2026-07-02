"""
email_publisher.py
Single email to all recipients — card grid layout, team tags, dynamic buckets.
Gmail-safe: table-based layout, inline styles only.
"""
from __future__ import annotations
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bot.config import GMAIL_SENDER, GMAIL_APP_PASSWORD, EMAIL_ALL

log = logging.getLogger(__name__)

# ── Colour palette (one per team tag) ─────────────────────────────────────────
TEAM_COLORS = {
    'Tech':        {'bg': '#1F4E78', 'light': '#E8F0F8'},
    'Risk':        {'bg': '#7030A0', 'light': '#F3EAF8'},
    'CX':          {'bg': '#C00000', 'light': '#FCE8E8'},
    'Payments':    {'bg': '#ED7D31', 'light': '#FDF0E6'},
    'Product':     {'bg': '#2E75B6', 'light': '#E6F0FA'},
    'Ops':         {'bg': '#375623', 'light': '#E8F2E6'},
    'Compliance':  {'bg': '#7B3F00', 'light': '#F5EDE6'},
    'default':     {'bg': '#595959', 'light': '#F0F0F0'},
}

def _colors(team_tag: str) -> dict:
    return TEAM_COLORS.get(team_tag, TEAM_COLORS['default'])


def _delta_html(n: int) -> str:
    if n > 0:  return f'<span style="color:#C00000;font-weight:bold">↑ +{n} vs last week</span>'
    if n < 0:  return f'<span style="color:#375623;font-weight:bold">↓ {n} vs last week</span>'
    return '<span style="color:#888">→ same as last week</span>'


def _score_color(s: float) -> str:
    if s >= 7: return '#375623'
    if s >= 4: return '#ED7D31'
    return '#C00000'


# ── Issue card (Gmail-safe table) ──────────────────────────────────────────────

def _issue_card(cat: str, count: int, delta: int, team_tag: str, data: dict) -> str:
    colors   = _colors(team_tag)
    bg       = colors['bg']
    light    = colors['light']
    subs     = data.get('sub_categories', {})
    examples = data.get('examples', [])

    # Sub-issues — top 3 by count
    sub_html = ''
    for sub, n in sorted(subs.items(), key=lambda x: -x[1])[:3]:
        sub_html += (
            f'<tr><td style="padding:2px 0;font-size:12px;color:#444">'
            f'• {sub}: <strong>{n}</strong></td></tr>'
        )

    # One example quote
    ex_html = ''
    if examples:
        ex = examples[0]
        ex_html = (
            f'<tr><td style="padding:8px 0 0 0">'
            f'<div style="background:#F8F8F8;border-left:3px solid {bg};padding:6px 8px;'
            f'font-size:11px;color:#555;font-style:italic;border-radius:0 4px 4px 0">'
            f'{ex}</div></td></tr>'
        )

    team_pill = ''
    if team_tag:
        team_pill = (
            f'<span style="background:rgba(255,255,255,0.25);border-radius:4px;'
            f'padding:2px 7px;font-size:11px;font-weight:bold;margin-left:8px">'
            f'{team_tag}</span>'
        )

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="border-radius:10px;overflow:hidden;border:1px solid #E0E0E0;background:#fff">
      <!-- Card header -->
      <tr>
        <td style="background:{bg};padding:10px 14px;border-radius:10px 10px 0 0">
          <span style="color:#fff;font-weight:bold;font-size:13px">{cat}</span>{team_pill}
        </td>
      </tr>
      <!-- Count + delta -->
      <tr>
        <td style="padding:12px 14px 4px 14px;background:{light}">
          <span style="font-size:34px;font-weight:bold;color:{bg}">{count}</span>
          <span style="font-size:12px;color:#666;margin-left:6px">reviews</span><br>
          <span style="font-size:12px">{_delta_html(delta)}</span>
        </td>
      </tr>
      <!-- Sub-issues -->
      <tr>
        <td style="padding:10px 14px 4px 14px">
          <table width="100%" cellpadding="0" cellspacing="0">{sub_html}</table>
        </td>
      </tr>
      <!-- Example quote -->
      <tr>
        <td style="padding:0 14px 12px 14px">
          <table width="100%" cellpadding="0" cellspacing="0">{ex_html}</table>
        </td>
      </tr>
    </table>"""


# ── Full email builder ─────────────────────────────────────────────────────────

def _build_html(digest: dict) -> str:
    date_range  = digest['date_range']
    prev_range  = digest.get('prev_date_range', 'N/A')
    total       = digest['total']
    prev_total  = digest.get('prev_total', 0)
    total_delta = digest.get('total_delta', 0)
    neg         = digest['by_sentiment'].get('Negative', 0)
    neu         = digest['by_sentiment'].get('Neutral', 0)
    pos         = digest['by_sentiment'].get('Positive', 0)
    score       = digest['sentiment_score']
    prev_score  = digest.get('prev_score')
    top_issues  = digest['top_issues']   # (cat, count, delta, team_tag)
    spikes      = digest.get('spikes', [])
    sc          = _score_color(score)

    # Score trend
    if prev_score is not None:
        diff       = round(score - prev_score, 1)
        strend     = f'↑ +{diff}' if diff > 0 else f'↓ {diff}' if diff < 0 else '→ unchanged'
        strend_col = '#375623' if diff > 0 else '#C00000' if diff < 0 else '#888'
    else:
        strend, strend_col = 'First run', '#888'

    # ── Spike / alert banner ──────────────────────────────────────
    spike_html = ''
    if spikes:
        rows = ''.join(
            f'<tr>'
            f'<td style="padding:5px 12px;font-weight:bold;color:#7D4E00">{cat}</td>'
            f'<td style="padding:5px 12px;color:#555">{count} reviews</td>'
            f'<td style="padding:5px 12px;font-weight:bold;color:#C00000">{label}</td>'
            f'<td style="padding:5px 12px"><span style="background:#E0D0F0;border-radius:4px;'
            f'padding:2px 6px;font-size:11px">{tag}</span></td>'
            f'</tr>'
            for cat, count, label, tag in spikes
        )
        spike_html = f"""
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:#FFF3CD;border-left:5px solid #ED7D31;border-radius:0 8px 8px 0;
                      margin-bottom:24px">
          <tr><td style="padding:12px 16px 6px 16px;font-weight:bold;font-size:14px;color:#7D4E00">
            ⚠️ Alerts — New Issues or Spikes This Week
          </td></tr>
          <tr><td style="padding:0 8px 10px 8px">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr style="background:#FFE8A0">
                <th style="padding:5px 12px;text-align:left;font-size:12px">Issue</th>
                <th style="padding:5px 12px;text-align:left;font-size:12px">Count</th>
                <th style="padding:5px 12px;text-align:left;font-size:12px">Signal</th>
                <th style="padding:5px 12px;text-align:left;font-size:12px">Team</th>
              </tr>
              {rows}
            </table>
          </td></tr>
        </table>"""

    # ── Card grid (2 columns, Gmail-safe tables) ──────────────────
    cards_html = ''
    display_issues = [(c, n, d, t) for c, n, d, t in top_issues
                      if c != 'Uncategorized / No Text']

    for i in range(0, len(display_issues), 2):
        left_cat, left_n, left_d, left_t = display_issues[i]
        left_card = _issue_card(
            left_cat, left_n, left_d, left_t,
            digest['by_category'].get(left_cat, {})
        )
        if i + 1 < len(display_issues):
            right_cat, right_n, right_d, right_t = display_issues[i+1]
            right_card = _issue_card(
                right_cat, right_n, right_d, right_t,
                digest['by_category'].get(right_cat, {})
            )
        else:
            right_card = ''

        cards_html += f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px">
          <tr>
            <td width="48%" valign="top">{left_card}</td>
            <td width="4%"></td>
            <td width="48%" valign="top">{right_card}</td>
          </tr>
        </table>"""

    # ── Top 3 action items ────────────────────────────────────────
    action_rows = ''
    for rank, (cat, count, delta, tag) in enumerate(display_issues[:3], 1):
        colors    = _colors(tag)
        action_rows += (
            f'<tr><td style="padding:6px 0;font-size:13px">'
            f'<span style="background:{colors["bg"]};color:#fff;border-radius:4px;'
            f'padding:2px 8px;font-weight:bold;margin-right:8px">{rank}</span>'
            f'<strong style="color:{colors["bg"]}">{cat}</strong>'
            f' — {count} reviews &nbsp;{_delta_html(delta)}'
            f'&nbsp;&nbsp;<span style="background:{colors["light"]};border-radius:4px;'
            f'padding:1px 6px;font-size:11px;color:{colors["bg"]}">{tag}</span>'
            f'</td></tr>'
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#EEF2F7;font-family:Arial,sans-serif;color:#222">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:24px 12px">
<table width="640" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;
       overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08)">

  <!-- Header -->
  <tr><td style="background:#1F4E78;padding:24px 28px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <div style="font-size:22px;font-weight:bold;color:#fff">📊 StashFin Play Store Reviews</div>
        <div style="font-size:13px;color:rgba(255,255,255,0.75);margin-top:4px">
          {date_range} &nbsp;|&nbsp; 1-2-3★ reviews only &nbsp;|&nbsp; vs {prev_range}
        </div>
      </td>
    </tr></table>
  </td></tr>

  <!-- KPI strip -->
  <tr><td style="background:#F0F4FA;padding:0">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="20%" align="center" style="padding:18px 8px;border-right:1px solid #DDE5EF">
        <div style="font-size:30px;font-weight:bold;color:#1F4E78">{total}</div>
        <div style="font-size:11px;color:#666;margin-top:2px">Total 1-2-3★</div>
        <div style="font-size:11px;margin-top:2px">{_delta_html(total_delta)}</div>
      </td>
      <td width="20%" align="center" style="padding:18px 8px;border-right:1px solid #DDE5EF">
        <div style="font-size:30px;font-weight:bold;color:#C00000">{neg}</div>
        <div style="font-size:11px;color:#666;margin-top:2px">Negative</div>
        <div style="font-size:11px;color:#888;margin-top:2px">issue in text</div>
      </td>
      <td width="20%" align="center" style="padding:18px 8px;border-right:1px solid #DDE5EF">
        <div style="font-size:30px;font-weight:bold;color:#ED7D31">{neu}</div>
        <div style="font-size:11px;color:#666;margin-top:2px">Neutral</div>
        <div style="font-size:11px;color:#888;margin-top:2px">no text left</div>
      </td>
      <td width="20%" align="center" style="padding:18px 8px;border-right:1px solid #DDE5EF">
        <div style="font-size:30px;font-weight:bold;color:#375623">{pos}</div>
        <div style="font-size:11px;color:#666;margin-top:2px">Positive</div>
        <div style="font-size:11px;color:#888;margin-top:2px">positive text</div>
      </td>
      <td width="20%" align="center" style="padding:18px 8px">
        <div style="font-size:30px;font-weight:bold;color:{sc}">{score}
          <span style="font-size:14px">/10</span></div>
        <div style="font-size:11px;color:#666;margin-top:2px">Sentiment Score</div>
        <div style="font-size:11px;color:{strend_col};margin-top:2px">{strend}</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:24px 28px">

    {spike_html}

    <!-- Section title -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px">
      <tr><td style="border-bottom:2px solid #E5EAF0;padding-bottom:8px">
        <span style="font-size:16px;font-weight:bold;color:#1F4E78">
          Issue Breakdown — {len(display_issues)} categories found this week
        </span>
        <span style="font-size:12px;color:#888;margin-left:8px">
          Coloured tag = team that owns this issue
        </span>
      </td></tr>
    </table>

    {cards_html}

    <!-- Top 3 actions -->
    <table width="100%" cellpadding="0" cellspacing="0"
           style="background:#F0F4FA;border-radius:8px;margin-top:8px">
      <tr><td style="padding:16px 20px">
        <div style="font-size:14px;font-weight:bold;color:#1F4E78;margin-bottom:10px">
          🎯 Top 3 Things Needing Action This Week
        </div>
        <table width="100%" cellpadding="0" cellspacing="0">
          {action_rows}
        </table>
      </td></tr>
    </table>

  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#F0F4FA;padding:14px 28px;
                  border-top:1px solid #E5EAF0;font-size:11px;color:#999">
    Auto-generated by StashFin Review Bot &nbsp;|&nbsp;
    Covers {date_range} &nbsp;|&nbsp;
    1-2-3★ reviews only &nbsp;|&nbsp;
    Buckets discovered dynamically by Gemini each week &nbsp;|&nbsp;
    Contact Vishal (Marketing) for queries
  </td></tr>

</table>
</td></tr></table>
</body></html>"""
    return html


# ── Send ───────────────────────────────────────────────────────────────────────

def publish_via_email(digest: dict) -> None:
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        log.warning('Gmail credentials not set — skipping email')
        return
    if not EMAIL_ALL:
        log.warning('EMAIL_ALL is empty — no recipients configured')
        return

    html  = _build_html(digest)
    top   = digest['top_issues']
    spikes = digest.get('spikes', [])

    top_issue  = top[0][0] if top else 'No issues'
    date_range = digest['date_range']
    alert_flag = f' ⚠️ {spikes[0][0]} spike' if spikes else ''
    subject    = (
        f'StashFin Reviews | {date_range} | '
        f'{digest["total"]} reviews | {top_issue} highest{alert_flag}'
    )

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
        log.error(f'Email send failed: {e}')
        raise
