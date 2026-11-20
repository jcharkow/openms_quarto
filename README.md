# OpenMS community dashboard

Private dashboard combining the Tally sign-up survey, GitHub and Discord metrics.
Nightly: Python scripts fetch data into `data/*.parquet` → Quarto renders a static dashboard →
copied to a folder served by nginx/Caddy behind a login.

```
ingest/common.py            shared cleaning helpers + survey column names
ingest/tally.py             Tally API (or CSV export) -> survey_respondents, survey_choices
ingest/github.py            stars, issues/PRs, commits, discussions, contributors, releases, traffic, daily counts
ingest/packages.py          monthly Bioconda + PyPI downloads (public data)
ingest/discord_snapshot.py  member list with join dates, daily member counts, message counts per channel/author
dashboard/index.qmd         the Quarto dashboard (pages: Overview, Survey, GitHub, Discord, Survey → activity)
refresh.sh                  fetch everything, render, deploy
openms_survey_report.py     the old one-off PDF report (still works, uses ingest/common.py)
```

**Privacy:** names and emails are dropped during ingest (emails become a hash, only used to
count unique people). GitHub/Discord handles are kept so sign-ups can be matched to activity —
the site must stay behind a login. No Discord message content is stored.

## Setup (server)

```bash
# 1. Quarto: https://quarto.org/docs/download/  (tested with 1.12.1)
# 2. Python env
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 3. Secrets
cp .env.example .env && chmod 600 .env && $EDITOR .env
# 4. First run
./refresh.sh
```

Tokens:
- **Tally**: Settings → API keys. Form ID is in the form URL.
- **GitHub**: fine-grained token. Public read is enough for stars/issues; listing stargazers
  needs *any* token. Traffic (views/clones) needs "Administration: read" on the repo — without
  it, that card stays empty. GitHub keeps only 14 days of traffic, so history builds from the first run.
- **Discord**: create an app + bot at <https://discord.com/developers/applications>, invite it with
  *View Channels* + *Read Message History*, and under Bot → Privileged Gateway Intents switch on
  **Server Members Intent** (gives the member list with join dates). Server ID: enable developer
  mode, right-click the server. The member chart is reconstructed from current members' join dates
  (people who left are missing); exact counts and who-left tracking start from the first run.

Cron (nightly at 03:00):

```cron
0 3 * * * /path/to/repo/refresh.sh >> /var/log/openms-dashboard.log 2>&1
```

If one source fails, the others still update and the dashboard still renders; the script exits 1.

Serving with a login — nginx example:

```nginx
location /community/ {
    alias /var/www/openms-dashboard/;
    auth_basic "OpenMS";
    auth_basic_user_file /etc/nginx/.htpasswd;   # htpasswd -c /etc/nginx/.htpasswd <user>
}
```

## Day to day

- Tests (also run by GitHub Actions on every PR): `pip install -r requirements-dev.txt && python -m pytest tests`,
  plus a fake-data render — see AGENTS.md "Testing". The PR's Actions run has the rendered page as
  a downloadable `dashboard-preview` artifact.

- Live-edit the dashboard: `cd dashboard && quarto preview index.qmd`
- Use a manual CSV instead of the API: `.venv/bin/python -m ingest.tally --csv export.csv`
- Check what the Tally API returns: `... -m ingest.tally --dump-raw raw.json` (contains personal data — delete after)
- PDF report: `.venv/bin/python openms_survey_report.py export.csv -o report.pdf`
- Data lives in `data/` (override with `OPENMS_DATA_DIR`). Back it up: Discord and traffic history can't be re-fetched.
