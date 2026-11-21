# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, etc.) working in this repo. Human docs: README.md.

## What this is

A private, self-hosted dashboard for the OpenMS community: Tally sign-up survey + GitHub + Discord.
Nightly `refresh.sh`: `ingest/*.py` fetch APIs → `data/*.parquet` → Quarto renders
`dashboard/index.qmd` to static HTML → rsync to a web folder behind a login.

Why Quarto: chosen over Evidence.dev (its OSS framework was deprecated for the hosted Evidence
Studio in 2026). Keep it lightweight: no database, no app server, no SaaS in the data path.

## Layout

| Path | Role |
|---|---|
| `ingest/common.py` | Survey column names, cleaning helpers, `tidy_survey`, `read_table`/`write_table`, `DATA_DIR` |
| `ingest/tally.py` | Tally API (or `--csv`) → `survey_respondents`, `survey_choices` |
| `ingest/github.py` | → `github_daily`, `github_stars`, `github_issues`, `github_contributors`, `github_releases`, `github_traffic`, `github_commits`, `github_discussions`, `github_repo_services` |
| `ingest/packages.py` | → `package_downloads`, `package_services` (Bioconda monthly parquet + ClickPy/PyPI, public) |
| `FUNDER_METRICS.md` | Which de.NBI report KPIs are automated on the Funder KPIs page and which are still missing |
| `ingest/discord_snapshot.py` | → `discord_daily`, `discord_members`, `discord_messages` |
| `dashboard/index.qmd` | The whole dashboard (one file, `#` headings = pages) |
| `Dockerfile`, `docker-compose.yml`, `docker-refresh.sh` | Image with Python deps + Quarto running `refresh.sh`. Compose passes `.env` via `env_file` (pinned paths in `environment:` win), mounts `data/` + site dir; `docker-refresh.sh` runs it as the host user. CI builds it, renders fake data inside and checks the `.env` pass-through |
| `setup.sh` | Creates/repairs `.venv` (uv or venv+pip); `refresh.sh` calls it on first run or when `requirements.txt` changes |
| `scripts/make_fake_data.py` | Fake data for every table, for offline testing |
| `scripts/check_render.py` | Prints value boxes / placeholders of a rendered page; fails on tracebacks (`--strict`: also on placeholders) |
| `tests/` | pytest unit tests for ingest + survey cleaning (fake API clients, no network) |
| `.github/workflows/test.yml` | CI: pytest + fake-data render on PRs |
| `openms_survey_report.py` | Legacy PDF report from a CSV export; imports `ingest/common.py` |

Ingest modules run as `python -m ingest.<name>` from the repo root.

## Hard rules

- **Privacy.** Names and emails never leave `ingest/tally.py`: emails become `email_hash`, names
  become `has_name`. Do not add raw PII columns to any table. No Discord message content. Handles
  (GitHub/Discord) are kept on purpose for matching — the site is private.
- **No third-party data processors** (Google Sheets, hosted BI, etc.) for survey data without
  asking the user first.
- **Never commit** `.env`, `data/`, CSV exports, PDFs, or rendered output (see `.gitignore`).
- **Never run ingest or `make_fake_data.py` against the real `data/` while testing.** Set
  `OPENMS_DATA_DIR` to a scratch directory. `make_fake_data.py` refuses real `data/` unless `--force`.
- **History is irreplaceable.** `discord_daily`, `discord_members` (left_seen), `github_daily` and
  `github_traffic` accumulate over runs and cannot be re-fetched. Ingest changes must merge with
  existing tables (`upsert` pattern), never drop old rows.

## Conventions

- Tables are parquet, written atomically via `write_table(df, name)`; read with `read_table(name)`,
  which returns `None` if the table doesn't exist yet.
- Timestamps: naive UTC (`pd.to_datetime(..., utc=True).tz_localize(None)`).
- Usernames/handles: lower-cased. Survey handles go through `clean_github_handle` /
  `clean_discord_handle`.
- Every ingest script fails independently; `refresh.sh` keeps going and exits 1 if any failed.
  Optional API parts (no token, missing permission) print a hint and skip instead of crashing.
- Dashboard cells must tolerate any table being `None` or empty: use `none_msg("...")`.
  Value boxes: a cell with `#| content: valuebox`, `#| title: ...`, ending in
  `dict(icon=<bootstrap icon>, color=..., value=...)`. Charts: Plotly Express with `BLUE`/`ORANGE`,
  `margin=dict(l=10, r=10, t=10, b=10)`. Tables: `itables.show(...)`.
- Target pandas ≥ 2.1 including pandas 3 (string dtype default, copy-on-write).

## Testing

CI (`.github/workflows/test.yml`, on every PR and push to master/main) runs both of these;
run them locally before pushing:

```bash
pip install -r requirements-dev.txt
python -m pytest tests                       # ingest logic with fake API clients, no network

export OPENMS_DATA_DIR=$(mktemp -d)          # dashboard render with fake data
python scripts/make_fake_data.py
(cd dashboard && quarto render index.qmd)
python scripts/check_render.py dashboard/index.html --strict
rm -rf dashboard/index.html dashboard/index_files dashboard/.quarto
```

`--strict` fails if any card shows a placeholder, so a new table needs fake rows in
`make_fake_data.py`. CI also renders with an empty data dir (first-run state) and uploads the
fake-data dashboard as the `dashboard-preview` artifact.

Ingest tests live in `tests/`: subclass the API client (`FakeDiscord`, `FakeGitHub`), use the
`data_dir` fixture, and call `main()` twice to check incremental merge and de-duplication.
See `.claude/skills/` for step-by-step workflows.

## Known gotchas

- Funder KPIs: periods come from `kpi_periods()` (last 3 full calendar years + current YTD); never
  hard-code years. Funder counts use `issues_all` (bots included), not the bot-filtered `issues`.
  Repo/package → service mapping is in `GITHUB_REPOS` / `BIOCONDA_PACKAGES` / `PYPI_PACKAGES`
  (`name=core|python`, parsed by `parse_mapping`).
- Bioconda monthly files are ~10 MB each; `ingest.packages` skips months it already has. Don't
  backfill many months in tests.
- GitHub `/stargazers` requires a token (401 anonymously); traffic needs push/admin access.
  Anonymous rate limit is 60 req/h — test against small repos (e.g. `OpenMS/umetaflow`).
- Discord member list needs the bot's **Server Members Intent**; without it the API returns 403.
  Discord IDs are snowflakes: page with `after=max(id)`, not list order.
- Tally API answer shapes vary by question type (labels, option ids, objects); `tally._label`
  handles the known cases. Untitled checkbox questions become `Untitled checkboxes field (<option>)`
  to match the CSV export.
- Plotly rejects a Python `range` for `y`: use a list.
- `refresh.sh`: variables already set in the environment win over `.env` (Docker sets
  `PYTHON`, `QUARTO`, `DEPLOY_DIR`, `HOME`). Keep it that way.
- `refresh.sh` uses `realpath -s` so a venv's python symlink isn't resolved to system python.
- Quarto needs `jupyter` in the same Python (`QUARTO_PYTHON`).
