"""
email_publisher.py
Sends rich HTML digest emails to each team.
Uses Gmail SMTP with App Password — no OAuth needed.
"""
from __future__ import annotations
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bot.config import GMAIL_SENDER, GMAIL_APP_PASSWORD, EMAIL_TEAMS
from bot.digest import filter_for_team

log = logging.getLogger(__name__)

CAT_COLORS = {
    'Fraud / Scam':                  '#7030A0',
    'Fees & Charges':                '#ED7D31',
    'EMI / Payment Issues':          '#C00000',
    'Loan Eligibility / Processing': '#2E75B6',
    'Customer Support':              '#FF0000',
    'Technical Issues':              '#1F4E78',
    'KYC / Verification Issues':     '#8B5A2B',
    'Data Privacy / Harassment':     '#7B3F00',
    'Refund Issues':                 '#375623',
    'Digital Gold / Rewards Issues': '#B8860B',
    'UI/UX & Feature Feedback':      '#4472C4',
    'Other / Vague':                 '#888888',
    'Uncategorized / No Text':       '#AAAAAA',
}


def _delta_str(n: int) -> str:
    if n > 0:  return f'<span style="color:#C00000">↑ +{n} vs last week</span>'
    if n < 0:  return f'<span style="color:#375623">↓ {n} vs last week</span>'
    return '<span style="color:#888">→ same as last week</span>'


def _score_color(score: float) -> str:
    if score >= 7:  return '#375623'
    if score >= 5:  return '#ED7D31'
    return '#C00000'


def _build_html(digest: dict, team_name: str) -> str:
    date       = digest['generated_at']
    prev_date  = digest.get('prev_date', 'N/A')
    total      = digest['total']
    prev_total = digest.get('prev_total', 0)
    neg        = digest['by_sentiment'].get('Negative', 0)
    neu        = digest['by_sentiment'].get('Neutral', 0)
    pos        = digest['by_sentiment'].get('Positive', 0)
    score      = digest['sentiment_score']
    prev_score = digest.get('prev_score')
    spikes     = digest.get('spikes', [])
    top_issues = digest['top_issues']

    score_color  = _score_color(score)
    total_delta  = digest.get('total_delta', 0)

    # Score trend line
    if prev_score is not None:
        score_diff  = round(score - prev_score, 1)
        score_trend = (f'↑ +{score_diff} vs last week' if score_diff > 0
                       else f'↓ {score_diff} vs last week' if score_diff < 0
                       else '→ unchanged')
        score_trend_color = '#375623' if score_diff > 0 else '#C00000' if score_diff < 0 else '#888'
    else:
        score_trend       = 'First run — no comparison available'
        score_trend_color = '#888'

    # ── Spike / New Issue Alert block ─────────────────────────────
    spike_html = ''
    if spikes:
        spike_rows = ''.join(
            f'<tr><td style="padding:6px 12px;font-weight:bold;color:{CAT_COLORS.get(c,"#333")}">'
            f'{c}</td><td style="padding:6px 12px">{n} reviews</td>'
            f'<td style="padding:6px 12px;color:#C00000;font-weight:bold">{label}</td></tr>'
            for c, n, label in spikes
        )
        spike_html = f"""
        <div style="background:#FFF3CD;border-left:4px solid #ED7D31;padding:16px 20px;margin-bottom:24px;border-radius:0 8px 8px 0">
          <div style="font-weight:bold;font-size:15px;color:#7D4E00;margin-bottom:10px">⚠️ Alerts — New Issues or Spikes This Week</div>
          <table style="width:100%;border-collapse:collapse">
            <tr style="background:#FFE8A0"><th style="padding:6px 12px;text-align:left">Issue</th>
            <th style="padding:6px 12px;text-align:left">Count</th>
            <th style="padding:6px 12px;text-align:left">Signal</th></tr>
            {spike_rows}
          </table>
        </div>"""

    # ── Issue breakdown rows ───────────────────────────────────────
    issue_rows_html = ''
    for cat, count, delta in top_issues:
        data  = digest['by_category'].get(cat, {})
        subs  = data.get('sub_categories', {})
        exs   = data.get('examples', [])
        color = CAT_COLORS.get(cat, '#888')

        sub_html = ''.join(
            f'<div style="padding:2px 0;font-size:13px;color:#444">'
            f'&nbsp;&nbsp;• <strong>{s}</strong>: {n}</div>'
            for s, n in sorted(subs.items(), key=lambda x: -x[1])
        )
        ex_html = ''.join(
            f'<div style="background:#F8F8F8;border-left:3px solid #DDD;padding:8px 12px;'
            f'margin:4px 0;font-size:13px;color:#555;font-style:italic;border-radius:0 4px 4px 0">'
            f'{e}</div>'
            for e in exs[:2]
        )

        issue_rows_html += f"""
        <div style="margin-bottom:24px;border-left:4px solid {color};padding-left:14px">
          <div style="display:flex;align-items:baseline;gap:12px">
            <span style="font-size:16px;font-weight:bold;color:{color}">{cat}</span>
            <span style="font-size:26px;font-weight:bold;color:{color}">{count}</span>
            <span style="font-size:13px">{_delta_str(delta)}</span>
          </div>
          <div style="margin:8px 0">{sub_html}</div>
          <div style="margin-top:8px;font-size:13px;font-weight:bold;color:#666">Sample reviews this week:</div>
          {ex_html}
        </div>"""

    # ── What needs action ──────────────────────────────────────────
    action_items = top_issues[:3]
    action_html  = ''.join(
        f'<li style="margin-bottom:6px"><strong style="color:{CAT_COLORS.get(c,"#333")}">{c}</strong>'
        f' — {n} reviews {_delta_str(d)}</li>'
        for c, n, d in action_items
    )

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>StashFin Reviews — {date}</title></head>
<body style="margin:0;padding:0;background:#F0F4F8;font-family:Arial,sans-serif;font-size:14px;color:#222">
<div style="max-width:680px;margin:24px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">

  <!-- Header -->
  <div style="background:#1F4E78;padding:24px 28px;color:#fff">
    <div style="font-size:22px;font-weight:bold">📊 StashFin Play Store Reviews</div>
    <div style="font-size:15px;margin-top:4px;opacity:0.85">Week of {date} &nbsp;|&nbsp; Team: {team_name}</div>
    <div style="font-size:13px;margin-top:4px;opacity:0.7">Comparison vs week of {prev_date} &nbsp;|&nbsp; 1-2-3★ reviews only</div>
  </div>

  <div style="padding:24px 28px">

    <!-- KPI row -->
    <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap">
      <div style="flex:1;min-width:100px;background:#F0F4FA;border-radius:8px;padding:14px;text-align:center">
        <div style="font-size:30px;font-weight:bold;color:#1F4E78">{total}</div>
        <div style="font-size:12px;color:#666;margin-top:2px">Total 1-2-3★</div>
        <div style="font-size:12px;color:#888">{_delta_str(total_delta)}</div>
      </div>
      <div style="flex:1;min-width:100px;background:#FFF0F0;border-radius:8px;padding:14px;text-align:center">
        <div style="font-size:30px;font-weight:bold;color:#C00000">{neg}</div>
        <div style="font-size:12px;color:#666;margin-top:2px">Negative</div>
        <div style="font-size:12px;color:#888">(issue found in text)</div>
      </div>
      <div style="flex:1;min-width:100px;background:#FFFBF0;border-radius:8px;padding:14px;text-align:center">
        <div style="font-size:30px;font-weight:bold;color:#ED7D31">{neu}</div>
        <div style="font-size:12px;color:#666;margin-top:2px">Neutral</div>
        <div style="font-size:12px;color:#888">(no text left)</div>
      </div>
      <div style="flex:1;min-width:100px;background:#F0FFF4;border-radius:8px;padding:14px;text-align:center">
        <div style="font-size:30px;font-weight:bold;color:#375623">{pos}</div>
        <div style="font-size:12px;color:#666;margin-top:2px">Positive</div>
        <div style="font-size:12px;color:#888">(positive text, low star)</div>
      </div>
      <div style="flex:1;min-width:100px;background:#F5F0FF;border-radius:8px;padding:14px;text-align:center">
        <div style="font-size:30px;font-weight:bold;color:{score_color}">{score}<span style="font-size:16px">/10</span></div>
        <div style="font-size:12px;color:#666;margin-top:2px">Sentiment Score</div>
        <div style="font-size:12px;color:{score_trend_color}">{score_trend}</div>
      </div>
    </div>

    <!-- Spike alerts -->
    {spike_html}

    <!-- Issue breakdown -->
    <div style="font-size:17px;font-weight:bold;color:#1F4E78;border-bottom:2px solid #E5EAF0;padding-bottom:8px;margin-bottom:20px">
      Issue Breakdown (with sub-category detail)
    </div>
    {issue_rows_html if issue_rows_html else '<p style="color:#888">No issues matching this team this week.</p>'}

    <!-- What needs action -->
    <div style="background:#F0F4FA;border-radius:8px;padding:16px 20px;margin-top:8px">
      <div style="font-size:15px;font-weight:bold;color:#1F4E78;margin-bottom:10px">🎯 Top 3 Things Needing Action This Week</div>
      <ol style="margin:0;padding-left:20px;line-height:1.8">{action_html}</ol>
    </div>

  </div>

  <!-- Footer -->
  <div style="background:#F0F4FA;padding:14px 28px;font-size:12px;color:#888;border-top:1px solid #E5EAF0">
    Auto-generated by StashFin Review Bot &nbsp;|&nbsp; 
    Covers {DAYS_TO_FETCH_STR} days ending {date} &nbsp;|&nbsp;
    Only 1-2-3★ reviews processed &nbsp;|&nbsp;
    Contact Vishal (Marketing) for queries
  </div>
</div>
</body></html>"""
    return html


# pulled from config at module level so template can reference it
from bot.config import DAYS_TO_FETCH
DAYS_TO_FETCH_STR = str(DAYS_TO_FETCH)


def _send(to: list[str], subject: str, html: str) -> None:
    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = GMAIL_SENDER
    msg['To']      = ', '.join(to)
    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_SENDER, to, msg.as_string())


def publish_via_email(digest: dict) -> None:
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        log.warning('Gmail credentials not configured — skipping email')
        return

    for team_name, cfg in EMAIL_TEAMS.items():
        recipients = cfg['recipients']
        categories = cfg['categories']
        if not recipients:
            log.info(f'No recipients for team "{team_name}" — skipping')
            continue

        team_digest = filter_for_team(digest, categories)
        if team_digest['total'] == 0:
            log.info(f'No reviews for team "{team_name}" this week — skipping')
            continue

        html      = _build_html(team_digest, team_name)
        top       = team_digest['top_issues']
        top_issue = top[0][0] if top else 'No issues'
        spikes    = team_digest.get('spikes', [])
        alert     = f' ⚠️ {spikes[0][0]} spiked' if spikes else ''
        subject   = (f'StashFin Reviews | Week of {digest["generated_at"]} | '
                     f'{team_digest["total"]} reviews | {top_issue} highest{alert}')

        try:
            _send(recipients, subject, html)
            log.info(f'Email sent to {recipients} [{team_name}]')
        except Exception as e:
            log.error(f'Email failed for {team_name}: {e}')
