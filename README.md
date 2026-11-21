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

## Setup with Docker (recommended)

The image contains Python, the dependencies and Quarto, so the host only needs Docker (with the
Compose plugin). Secrets, data and the rendered site stay on the host.

```bash
cp .env.example .env && chmod 600 .env && $EDITOR .env   # tokens: see "Tokens" below
./docker-refresh.sh                                      # one refresh: ingest + render -> ./site
```

`docker-refresh.sh` creates `data/` and `site/`, rebuilds the image from cache (fast; picks up a
`git pull`), and runs the container as your own user, so the files it writes stay yours (on rootless
Docker it runs as container root, which is you on the host). `./docker-refresh.sh bash` opens a shell
in the container for debugging.

- The rendered dashboard lands in `./site`; set `SITE_DIR=/var/www/openms-dashboard` in the
  environment to write elsewhere. Serve it behind a login (nginx example below).
- `data/` holds the parquet tables, including history that can't be re-fetched — back it up. It is
  the same folder the non-Docker setup uses, so you can switch between both.
- `docker-refresh.sh` loads `.env` with bash on the host (same rules as `refresh.sh`) and passes the
  values in; Docker never reads the file. `PYTHON`, `QUARTO`, `DEPLOY_DIR` and `OPENMS_DATA_DIR` from
  `.env` are ignored in the container (the image's paths win).
- If it reports files in `data/` or `site/` not owned by you (folders Docker created as root, e.g.
  from a plain `docker compose run`), fix once with `sudo chown -R $(id -u):$(id -g) data site`.

Nightly cron:

```cron
0 3 * * * /path/to/repo/docker-refresh.sh >> /var/log/openms-dashboard.log 2>&1
```

## Setup without Docker

```bash
# 1. Quarto: https://quarto.org/docs/download/  (tested with 1.12.1)
# 2. Python env: optional, refresh.sh runs this itself on the first run (uses uv if installed).
#    Re-run with --dev for pytest. Set PYTHON=... in .env to use another interpreter (e.g. conda).
./setup.sh
# 3. Secrets
cp .env.example .env && chmod 600 .env && $EDITOR .env
# 4. First run
./refresh.sh
```

Tokens (all go into `.env`):

**Tally**: Settings → API keys → `TALLY_API_KEY`. The form ID is in the form URL
(`tally.so/forms/<ID>`) → `TALLY_FORM_ID`.

**GitHub** (`GITHUB_TOKEN`): <https://github.com/settings/personal-access-tokens> → *Generate new
token* (fine-grained), repository access *Public repositories* (read-only) is enough for issues,
commits, releases, stargazers and discussions. Without any token, stargazers and discussions are
skipped and the 60 requests/hour limit makes larger repos fail. Traffic (views/clones) additionally
needs *Administration: read* on repos you own or admin; without it that card stays empty. GitHub keeps
only 14 days of traffic, so that history builds up from the first run. List the repos and their
service packages in `GITHUB_REPOS` (keep the quotes, see `.env.example` and `FUNDER_METRICS.md`).

**Discord** (`DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`): the bot only reads; it never posts and
stores no message text.

1. Go to <https://discord.com/developers/applications> → *New Application* (e.g. "OpenMS dashboard").
2. *Bot* tab:
   - *Reset Token* → copy it into `DISCORD_BOT_TOKEN` (shown once; treat it like a password).
   - Under *Privileged Gateway Intents* switch on **Server Members Intent** (member list with join
     dates). *Message Content Intent* is **not** needed. Save.
   - Optionally turn off *Public Bot* so nobody else can invite it.
3. Invite it to the server. This needs **Manage Server** (or Administrator) on the OpenMS server;
   without it, generate the link below and send it to a server admin.
   - Get an invite link: in the developer portal open *OAuth2 → URL Generator*, tick scope **bot**,
     then bot permissions **View Channels** and **Read Message History** (nothing else), keep
     *Guild Install*, and copy the *Generated URL*. Equivalent by hand, with the ID from
     *General Information → Application ID* (66560 = View Channels 1024 + Read Message History 65536):

     ```
     https://discord.com/oauth2/authorize?client_id=<APPLICATION_ID>&scope=bot&permissions=66560
     ```

   - Open the link in a browser logged into Discord, pick the OpenMS server under *Add to server*
     (only servers where you have Manage Server are listed), *Continue*, check the two permissions,
     *Authorize*, solve the captcha.
   - The bot now appears in the member list as **offline** — expected: it never connects live, it only
     reads the API once a night. Discord gives it a role named after the bot with those permissions.
   - To remove it later: right-click the bot → *Kick*, and reset the token in the developer portal.
4. Server ID: Discord → User Settings → Advanced → enable *Developer Mode*, then right-click the
   server icon → *Copy Server ID* → `DISCORD_GUILD_ID`.
5. Private channels are only counted if the bot's role can see them: *Edit Channel → Permissions →
   Add members or roles* → the bot's role → allow *View Channel* + *Read Message History*.
6. Test: `.venv/bin/python -m ingest.discord_snapshot`. A 403 on the member list means the Server
   Members Intent is off; a 401 means a wrong token.

The first run reads `DISCORD_BACKFILL_DAYS` (default 180) of message history; later runs are
incremental. The member chart is reconstructed from current members' join dates (people who left are
missing); exact counts and who-left tracking start from the first run. Threads and forum posts are not
counted.

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
