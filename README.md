# StashFin Review Bot

Automatically fetches 1-2-3★ Play Store reviews weekly, classifies them with Gemini,
and emails rich digest reports to each team. Runs on GitHub Actions — no server needed.

---

## Setup (one time, ~20 minutes)

### Step 1 — Create a GitHub repository

1. Go to github.com → New repository
2. Name it `stashfin-review-bot`
3. Set to Private
4. Upload all files from this zip into the repo

### Step 2 — Add GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

Add these one by one:

| Secret name         | Value                                      |
|---------------------|--------------------------------------------|
| GEMINI_API_KEY      | Your Gemini API key from AI Studio         |
| GMAIL_SENDER        | vishal.vijayvergiya@stashfin.com           |
| GMAIL_APP_PASSWORD  | Your 16-digit Gmail App Password           |
| EMAIL_PRODUCT       | email1@stashfin.com,email2@stashfin.com    |
| EMAIL_TECH          | techlead@stashfin.com                      |
| EMAIL_CX            | cxlead@stashfin.com                        |
| EMAIL_RISK          | risk@stashfin.com                          |

Note: EMAIL_* can have multiple addresses separated by commas.
Leave any EMAIL_* blank if that team does not need a digest yet.

### Step 3 — Enable GitHub Actions

Go to your repo → Actions tab → click "I understand my workflows, go ahead and enable them"

### Step 4 — Test it manually

Go to Actions → "StashFin Review Bot" → Run workflow → Run workflow

Watch the logs. First run will send emails and create last_run.json.
Every run after that will show trends vs the previous run.

---

## Schedule

Runs automatically every Monday at 9:00am IST.
Can also be triggered manually anytime from the Actions tab.

---

## Adding more team recipients

Edit `bot/config.py` → EMAIL_TEAMS section.
Add the team name, recipient env variable, and which categories they should receive.

## Adding Slack later (when approved)

Add `SLACK_WEBHOOK_URL` to GitHub Secrets.
We will add the Slack publisher module at that point.

---

## Files

```
stashfin-review-bot/
├── .github/workflows/review_bot.yml   ← scheduler
├── bot/
│   ├── config.py                      ← all settings
│   ├── fetcher.py                     ← pulls reviews from Play Store
│   ├── classifier.py                  ← Gemini classification
│   ├── digest.py                      ← builds weekly summary + trends
│   └── email_publisher.py             ← sends HTML emails
├── main.py                            ← entry point
├── requirements.txt
└── last_run.json                      ← auto-created, tracks weekly trends
```
