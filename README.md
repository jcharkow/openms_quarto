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

- Tests (also run by GitHub Actions on every PR): `pip install -r requirements-dev.txt && python -m pytest tests`,
  plus a fake-data render — see AGENTS.md "Testing". The PR's Actions run has the rendered page as
  a downloadable `dashboard-preview` artifact.

- Live-edit the dashboard: `cd dashboard && quarto preview index.qmd`
- Use a manual CSV instead of the API: `.venv/bin/python -m ingest.tally --csv export.csv`
- Check what the Tally API returns: `... -m ingest.tally --dump-raw raw.json` (contains personal data — delete after)
- PDF report: `.venv/bin/python openms_survey_report.py export.csv -o report.pdf`
- Data lives in `data/` (override with `OPENMS_DATA_DIR`). Back it up: Discord and traffic history can't be re-fetched.
