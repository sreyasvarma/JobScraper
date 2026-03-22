# 🎯 Job Alert — Never Miss a New Opening

Scrapes the careers pages of companies you care about and emails you the moment a new job appears. Designed to run for free on GitHub Actions, or locally via cron.

---

## Features

- ✅ Supports **static** (BeautifulSoup) and **JS-rendered** (Playwright) career pages
- ✅ **Diff engine** — only alerts on genuinely new postings, no duplicates
- ✅ **Keyword filtering** — include/exclude roles by keyword
- ✅ **Beautiful HTML email digest** grouped by company
- ✅ **SQLite storage** — lightweight, zero infrastructure
- ✅ **GitHub Actions** deployment — runs every 4 hours for free
- ✅ **Graceful error handling** — one bad scraper never blocks the others

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/you/job-alert.git
cd job-alert

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium    # Only needed for JS sites
```

### 2. Configure

Edit `config.yaml`:

```yaml
email:
  sender: "your_gmail@gmail.com"
  password: "xxxx xxxx xxxx xxxx"   # Gmail App Password
  recipient: "you@example.com"
```

**Getting a Gmail App Password:**
1. Enable 2FA on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an app called "Job Alert" — copy the 16-char password

### 3. Test it (dry run — no email sent)

```bash
python main.py --dry-run
```

### 4. Run for real

```bash
# Single check, then exit (great for cron)
python main.py --once

# Continuous loop (runs every N hours as set in config)
python main.py
```

---

## Adding a Company

Open `config.yaml` and add an entry to the `companies` list:

```yaml
- name: Acme Corp
  url: "https://acme.com/careers"
  type: static        # or "js" for React/SPA sites
  selectors:
    container: "a.job-link"        # CSS selector for each job card/link
    title: ".job-title"            # selector for the title within the card
    location: ".job-location"      # selector for location
```

**Tips for finding selectors:**
- Open the careers page in Chrome
- Right-click a job listing → Inspect
- Find the repeating element and right-click → Copy → Copy selector

---

## Keyword Filtering

In `config.yaml`:

```yaml
keywords_filter:
  include: ["engineer", "designer"]   # Only alert on these roles
  exclude: ["intern", "director"]     # Never alert on these
```

Leave `include` empty to get all roles.

---

## Deploy to GitHub Actions (Free)

1. Push this repo to GitHub (make it **private**)

2. Add secrets: `Settings → Secrets and variables → Actions`
   - `EMAIL_SENDER` — your Gmail address
   - `EMAIL_PASSWORD` — your App Password
   - `EMAIL_RECIPIENT` — where to send alerts

3. Enable Actions: `Actions → Enable workflows`

4. The workflow runs automatically every 4 hours. You can also trigger it manually from the Actions tab.

---

## Running via Cron (Local)

```bash
# Edit crontab
crontab -e

# Add this line (runs every 4 hours):
0 */4 * * * cd /path/to/job-alert && /path/to/venv/bin/python main.py --once
```

---

## Project Structure

```
job-alert/
├── scrapers/
│   ├── __init__.py
│   ├── base.py          # Job dataclass + BaseScraper ABC
│   └── generic.py       # Config-driven static + JS scrapers
├── storage.py           # SQLite storage layer
├── diff.py              # New job detection + keyword filter
├── notifier.py          # HTML email digest
├── main.py              # Orchestrator + CLI entry point
├── config.yaml          # All configuration lives here
├── requirements.txt
└── .github/
    └── workflows/
        └── job-alert.yml
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `playwright install` fails | Run `playwright install chromium --with-deps` |
| Email not sending | Double-check App Password, ensure 2FA is on |
| No jobs found | Inspect the site and update CSS selectors in config |
| JS site not loading | Increase `wait_for_timeout` in `generic.py` |
| Getting duplicates | Delete `jobs.db` to reset the seen-jobs store |

---

## License

MIT — do whatever you want with it.
