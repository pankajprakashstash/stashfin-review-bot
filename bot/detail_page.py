"""
detail_page.py — Generates index.html for GitHub Pages.
Full detail view with Chart.js trend, historical table, all issue cards.
"""
from __future__ import annotations
import json
import logging
from bot.config import (BRAND_CORAL, BRAND_BLUE, BRAND_CORAL_LT,
                         BRAND_BLUE_LT, TABLE_WEEKS)

log = logging.getLogger(__name__)
EXCLUDE = {'Uncategorized / No Text', 'Irrelevant / Gibberish', 'Positive Feedback'}


def _safe(s: str) -> str:
    return (str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
             .replace('"','&quot;').replace("'",'&#39;'))


def _delta_badge(n: int) -> str:
    if n > 0:  return f'<span style="color:{BRAND_CORAL};font-weight:700;">↑ +{n}</span>'
    if n < 0:  return f'<span style="color:#007A45;font-weight:700;">↓ {n}</span>'
    return '<span style="color:#888;">→</span>'


def _short_date(date_range: str) -> str:
    """Extract short week label from date range string. e.g. '19 Jun – 03 Jul 2026' → '19 Jun'"""
    if '–' in date_range:
        return date_range.split('–')[0].strip()
    if '-' in date_range:
        return date_range.split('-')[0].strip()
    return date_range[:8]


def _issue_card_html(cat: str, count: int, delta: int,
                     data: dict, color: str, is_new: bool) -> str:
    subs     = data.get('sub_categories', {})
    examples = data.get('examples', [])
    team     = data.get('team_tag', '')
    hdr_col  = '#00875A' if is_new else color

    team_pill = (f'<span style="background:rgba(255,255,255,.25);color:#fff;font-size:10px;'
                 f'padding:2px 8px;border-radius:10px;margin-left:8px;">{_safe(team)}</span>'
                 if team else '')

    new_badge = ('<span style="background:#fff;color:#00875A;font-size:10px;font-weight:700;'
                 'padding:2px 8px;border-radius:4px;margin-left:8px;">NEW</span>'
                 if is_new else '')

    delta_html = (f'<span style="color:rgba(255,255,255,.8);font-size:12px;">↑ +{delta} vs last week</span>' if delta > 0
                  else f'<span style="color:rgba(255,255,255,.8);font-size:12px;">↓ {delta} vs last week</span>' if delta < 0
                  else '<span style="color:rgba(255,255,255,.6);font-size:12px;">→ same as last week</span>')

    subs_html = ''
    if subs:
        rows = ''.join(
            f'<div style="display:flex;justify-content:space-between;padding:5px 0;'
            f'border-bottom:1px solid #F5F5F5;font-size:12px;">'
            f'<span style="color:#444;">{_safe(sub[:90])}{"…" if len(sub)>90 else ""}</span>'
            f'<strong style="color:{color};margin-left:8px;">{n}</strong></div>'
            for sub, n in sorted(subs.items(), key=lambda x: -x[1])[:5]
        )
        subs_html = (f'<div style="font-size:10px;font-weight:600;color:#AAA;text-transform:uppercase;'
                     f'letter-spacing:.5px;margin:12px 0 6px;">What users are saying</div>{rows}')

    quotes_html = ''
    if examples:
        quotes = ''.join(
            f'<div style="background:{BRAND_CORAL_LT};border-left:3px solid {color};padding:8px 12px;'
            f'margin:5px 0;border-radius:0 6px 6px 0;font-size:12px;color:#555;font-style:italic;">'
            f'{_safe(ex)}</div>'
            for ex in examples[:2]
        )
        quotes_html = (f'<div style="font-size:10px;font-weight:600;color:#AAA;text-transform:uppercase;'
                       f'letter-spacing:.5px;margin:12px 0 6px;">User voices</div>{quotes}')

    return f"""<div style="background:#fff;border-radius:12px;border:1.5px solid {hdr_col};
               margin-bottom:14px;overflow:hidden;">
  <div style="background:{hdr_col};padding:12px 20px;display:flex;
               justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
    <div>
      <span style="color:#fff;font-size:14px;font-weight:600;">{_safe(cat)}</span>
      {team_pill}{new_badge}
    </div>
    <div style="text-align:right;">
      <span style="color:#fff;font-size:26px;font-weight:700;">{count}</span>
      &nbsp;{delta_html}
    </div>
  </div>
  <div style="padding:14px 20px;">
    {subs_html}
    {quotes_html}
  </div>
</div>"""


def generate(digest: dict, output_path: str = 'index.html') -> None:
    date_range   = digest['date_range']
    prev_date    = digest.get('prev_date_range', 'N/A')
    total        = digest['total']
    weekly_total = digest.get('weekly_total', 0)
    avg_rating   = digest.get('avg_rating', 0.0)
    signal_rate  = digest.get('signal_rate', 0)
    top_issues   = digest['top_issues']
    trend_data   = digest.get('trend_data', {})
    history      = digest.get('history', [])
    color_map    = digest.get('color_map', {})
    by_category  = digest.get('by_category', {})
    spikes       = digest.get('spikes', [])
    generated    = digest.get('generated_at', '')
    new_cats     = {c for c,n,l in spikes if l=='NEW'}

    display = [(c,n,d,t,p) for c,n,d,t,p in top_issues if c not in EXCLUDE]

    # ── Chart.js data ──────────────────────────────────────────────
    chart_weeks  = [wk.get('date_range','') for wk in history[-7:]] + [date_range]
    chart_labels = chart_weeks
    datasets     = []
    colors_list  = [BRAND_CORAL,'#1B3A6B','#E07800','#6B35A0','#0077B6','#C0392B','#2C6E49']

    for i, (cat, count, *_) in enumerate(display[:6]):
        color  = color_map.get(cat, colors_list[i % len(colors_list)])
        series = trend_data.get(cat, [])
        cnt_by_date = {pt.get('date',''): pt.get('count',0) for pt in series}
        values = [cnt_by_date.get(wk, 0) for wk in chart_weeks]
        datasets.append({
            'label':           cat,
            'data':            values,
            'borderColor':     color,
            'backgroundColor': color + '20',
            'tension':         0.3,
            'fill':            False,
            'pointRadius':     4,
            'pointHoverRadius':6,
        })

    # ── Historical comparison table ────────────────────────────────
    table_history = history[-(TABLE_WEEKS-1):]
    table_weeks   = table_history + [{'date_range': date_range, 'by_category':
                                       {cat: {'count': n} for cat,n,*_ in display}}]
    n_table_cols  = len(table_weeks)

    if n_table_cols >= 2:
        thead_cols = ''.join(
            f'<th style="padding:8px 10px;text-align:center;'
            f'{"background:#FFF5F5;color:" + BRAND_CORAL + ";" if i==n_table_cols-1 else "color:#888;font-weight:500;"}'
            f'font-size:11px;white-space:nowrap;">'
            f'{wk.get("date_range","")}'
            f'</th>'
            for i, wk in enumerate(table_weeks)
        )
        tbody_rows = ''
        for cat, count, delta, tag, prev in display[:8]:
            color = color_map.get(cat, '#555')
            row   = f'<td style="padding:8px 10px;font-weight:600;color:{color};">{_safe(cat)}</td>'
            for i, wk in enumerate(table_weeks):
                wk_count = wk.get('by_category',{}).get(cat,{}).get('count',0)
                is_curr  = (i == n_table_cols - 1)
                row += (f'<td style="padding:8px 10px;text-align:center;'
                        f'{"background:#FFF5F5;font-weight:700;color:" + color + ";" if is_curr else "color:#555;"}'
                        f'font-size:12px;">{wk_count or "—"}'
                        f'{"" if not is_curr else " " + ("↓" if delta<0 else "↑" if delta>0 else "→")}'
                        f'</td>')
            tbody_rows += f'<tr style="border-bottom:1px solid #F5F5F5;">{row}</tr>'

        hist_table_html = f"""
        <div style="background:#fff;border-radius:12px;padding:18px 20px;
                    border:1px solid #E8EEF6;margin-bottom:20px;overflow-x:auto;">
          <div style="font-size:14px;font-weight:600;color:{BRAND_BLUE};margin-bottom:4px;">
            Week-over-week comparison</div>
          <div style="font-size:11px;color:#AAA;margin-bottom:12px;">
            Grows automatically — each Monday a new column is added (up to {TABLE_WEEKS} weeks shown)</div>
          <table style="width:100%;border-collapse:collapse;font-size:12px;min-width:400px;">
            <thead><tr style="background:{BRAND_BLUE_LT};">
              <th style="padding:8px 10px;text-align:left;color:{BRAND_BLUE};
                         font-size:12px;">Issue</th>
              {thead_cols}
            </tr></thead>
            <tbody>{tbody_rows}</tbody>
          </table>
        </div>"""
    else:
        hist_table_html = (f'<div style="background:#fff;border-radius:12px;padding:18px 20px;'
                           f'border:1px solid #E8EEF6;margin-bottom:20px;color:#AAA;font-size:13px;">'
                           f'Historical comparison table will appear from week 2 onwards.</div>')

    # ── All issue cards ────────────────────────────────────────────
    all_cards = ''.join(
        _issue_card_html(cat, count, delta,
                         by_category.get(cat, {}),
                         color_map.get(cat, '#555'),
                         cat in new_cats)
        for cat, count, delta, tag, prev in display
    )

    # ── Chart.js script ────────────────────────────────────────────
    chart_js = ''
    if len(chart_weeks) >= 2 and datasets:
        chart_js = f"""
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
        <script>
        document.addEventListener('DOMContentLoaded', function() {{
            new Chart(document.getElementById('trendChart'), {{
                type: 'line',
                data: {{
                    labels: {json.dumps(chart_labels)},
                    datasets: {json.dumps(datasets)}
                }},
                options: {{
                    responsive: true,
                    interaction: {{ mode: 'index', intersect: false }},
                    plugins: {{
                        legend: {{ position: 'bottom',
                                   labels: {{ font: {{ size: 11 }} }} }},
                        tooltip: {{ callbacks: {{ label: function(c) {{
                            return c.dataset.label + ': ' + c.parsed.y;
                        }} }} }}
                    }},
                    scales: {{
                        y: {{ beginAtZero: true,
                              grid: {{ color: '#F0F0F0' }},
                              ticks: {{ font: {{ size: 11 }} }} }},
                        x: {{ grid: {{ color: '#F0F0F0' }},
                              ticks: {{ font: {{ size: 10 }} }} }}
                    }}
                }}
            }});
        }});
        </script>"""

    # ── Full HTML ──────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>stashfin Play Store Reviews — {date_range}</title>
<style>
*{{box-sizing:border-box;}}
body{{margin:0;padding:0;background:#F5F7FA;
     font-family:'Helvetica Neue',Arial,sans-serif;color:#1A1A2E;}}
.container{{max-width:900px;margin:0 auto;padding:0 16px 32px;}}
canvas{{max-height:300px;}}
@media(max-width:600px){{
  .kpi-grid{{display:block!important;}}
  .kpi-tile{{margin-bottom:12px!important;}}
}}
</style>
</head><body>

<div style="background:{BRAND_CORAL};padding:18px 24px;">
  <div style="max-width:900px;margin:0 auto;display:flex;
               justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
    <div>
      <div style="font-size:11px;color:rgba(255,255,255,.8);font-weight:600;
                  letter-spacing:1.2px;">STASHFIN</div>
      <div style="font-size:18px;font-weight:600;color:#fff;margin-top:1px;">
        Play Store — Full Weekly Breakdown</div>
      <div style="font-size:11px;color:rgba(255,255,255,.7);margin-top:3px;">
        {date_range} &nbsp;|&nbsp; 1-2-3★ reviews only</div>
    </div>
    <div style="font-size:10px;color:rgba(255,255,255,.6);text-align:right;">
      Auto-updated every Monday<br>
      <span style="color:rgba(255,255,255,.9);">Generated: {generated}</span>
    </div>
  </div>
</div>

<div class="container">

  <div class="kpi-grid"
       style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0;">
    <div class="kpi-tile" style="background:#fff;border-radius:10px;padding:14px 16px;
                                  border:1px solid #E8EEF6;text-align:center;">
      <div style="font-size:30px;font-weight:700;color:{BRAND_BLUE};line-height:1;">
        {weekly_total or '—'}</div>
      <div style="font-size:11px;color:#888;margin-top:3px;">Total reviews</div>
    </div>
    <div class="kpi-tile" style="background:#fff;border-radius:10px;padding:14px 16px;
                                  border:1px solid #FFE5E5;text-align:center;">
      <div style="font-size:30px;font-weight:700;color:{BRAND_CORAL};line-height:1;">{total}</div>
      <div style="font-size:11px;color:#888;margin-top:3px;">1-2-3★ reviews</div>
    </div>
    <div class="kpi-tile" style="background:#fff;border-radius:10px;padding:14px 16px;
                                  border:1px solid #E8EEF6;text-align:center;">
      <div style="font-size:30px;font-weight:700;color:{BRAND_BLUE};line-height:1;">
        {avg_rating}{'★' if avg_rating else ''}</div>
      <div style="font-size:11px;color:#888;margin-top:3px;">Avg rating this week</div>
    </div>
    <div class="kpi-tile" style="background:#fff;border-radius:10px;padding:14px 16px;
                                  border:1px solid #E8EEF6;text-align:center;">
      <div style="font-size:30px;font-weight:700;color:#E07800;line-height:1;">
        {signal_rate}<span style="font-size:16px;">%</span></div>
      <div style="font-size:11px;color:#888;margin-top:3px;">Negative signal rate</div>
    </div>
  </div>

  <div style="background:#fff;border-radius:12px;padding:20px;
               border:1px solid #E8EEF6;margin-bottom:20px;">
    <div style="font-size:14px;font-weight:600;color:{BRAND_BLUE};margin-bottom:4px;">
      Issue trend — {len(chart_weeks)}-week view</div>
    <div style="font-size:11px;color:#AAA;margin-bottom:14px;">
      Top issues over time · hover for exact values</div>
    {'<canvas id="trendChart" style="max-height:300px;"></canvas>'
     if len(chart_weeks) >= 2 and datasets
     else '<div style="color:#AAA;font-size:13px;padding:20px 0;">Trend chart appears from week 2 onwards.</div>'}
  </div>

  {hist_table_html}

  <div style="font-size:14px;font-weight:600;color:{BRAND_BLUE};margin:24px 0 12px;">
    Detailed breakdown — {len(display)} issue areas this week
  </div>
  {all_cards}

  <div style="background:{BRAND_BLUE_LT};border-radius:10px;padding:14px 18px;
               margin-top:8px;font-size:11px;color:#888;line-height:1.7;">
    <strong style="color:{BRAND_BLUE};">Note:</strong>
    These reviews reflect user perception and may include misunderstandings, awareness gaps, or
    one-sided accounts. This report surfaces signals for discussion — not confirmed product failures.
    Each area should be investigated before conclusions are drawn.<br>
    Auto-generated by stashfin Review Bot · {date_range} · 1-2-3★ only ·
    Buckets discovered dynamically · Contact Vishal (Marketing)
  </div>

</div>
{chart_js}
</body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    log.info(f'Detail page written → {output_path}')
