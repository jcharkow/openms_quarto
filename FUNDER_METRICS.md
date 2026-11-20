# Funder metrics (de.NBI) — coverage

The **Funder KPIs** page of the dashboard rebuilds the numbers in the de.NBI status report
(Table 1 "Key Performance Indicators") and in the GitHub KPI evidence workbook prepared for the
2028–2032 application. Columns are the last three full calendar years plus the current year to
date (2023 | 2024 | 2025 | 2026 YTD in 2026); they roll forward every January.

Repos are listed in `GITHUB_REPOS` and tagged with the service package(s) they count towards:
`core` (Core + TOPP), `python` (Python libraries), `webapps`, `workflows`, e.g.
`OpenMS/OpenMS=core|python, OpenMS/streamlit-template=webapps, bigbio/quantms=workflows`.
Packages are tagged the same way in `BIOCONDA_PACKAGES` / `PYPI_PACKAGES`.

## Automated

| Metric (as in the PDFs) | Table / source | Notes |
|---|---|---|
| Merged PRs, PRs opened | `github_issues` (`merged_at`, `created_at`) | per repo, per service, all tracked repos |
| Issues opened / closed | `github_issues` | closure = current `closed_at` (stale/duplicate closures included) |
| GitHub support requests (issues + discussions) | `github_issues` + `github_discussions` | every opener counted, bots included, PRs excluded; discussions need a token |
| Commits, non-merge commits | `github_commits` | default branch, author date; backfill from `GITHUB_COMMITS_SINCE`. Each sha counted once across repos; "not shared" excludes commits that also appear in another tracked repo (template syncs, e.g. umetaflow ← streamlit-template). Won't match the PDF's per-repo figures for repos that synced history after its 13 Oct 2026 snapshot |
| Human commit-author accounts | `github_commits` | distinct non-bot logins; commits without a linked account excluded |
| Public releases (incl. prereleases) | `github_releases` | by `published_at` |
| Stars added (still present) | `github_stars` | needs a token; unstarred users are not visible |
| Lifetime release-asset downloads | `github_releases` | GitHub page; lifetime counters, no download dates |
| Bioconda downloads (libopenms, openms, openms-thirdparty, pyopenms) | `package_downloads` ← Anaconda public package data | monthly; available ~1 month after month end |
| PyPI downloads (pyopenms, pyopenms-viz) | `package_downloads` ← ClickPy (public PyPI download mirror) | 2025 totals reproduce the PDF exactly (1,412,749 / 36,808) |

## Not automated yet (to address later)

| Metric | Why not yet | Possible route |
|---|---|---|
| Citations (framework papers + NASE, pyOpenMS + viz, WebApps paper, quantms, MHCquant) | Google Scholar has no API and forbids scraping | OpenAlex or Semantic Scholar API per DOI (counts differ from Scholar; would need to re-baseline) |
| TOPP tool telemetry (tool calls / users per month) | Data lives in the private `OpenMS/UsageStatistics` repo / telemetry server | Ingest from the telemetry store or the repo's exports with a token |
| WebApp sessions, pageviews, workflow starts | Matomo/UsageStatistics, not wired up | Matomo Reporting API (`VisitsSummary.get`, `Actions.get`, `Goals.get`) with a token |
| WebApp annual unique visitors | Not retained before 2024 Q4; monthly uniques can't be summed | Matomo `VisitsSummary.get` with `period=year` from now on |
| Completed tool executions (TOPP) | No public source | Telemetry (above) |
| Completed workflow executions (quantms, MHCquant) | No public dated series; Docker pulls / CI runs are not executions | Seqera Platform / nf-core telemetry, if available |
| Training events and attendance | de.NBI training archive is HTML; attendance is only in organiser records | Scrape the CIBI archive page for events; attendance must come from organisers |
| Support response / closure times | Needs per-issue comment fetches (many API calls) | `/issues/{n}/comments` for issues in the reporting window, first non-author human reply |
| Discussion response times / accepted answers | Partly available (`answered_at` is stored) | Add first-reply time via GraphQL `comments(first:1)` |
| Installer / container downloads per year | GitHub release counters are lifetime only; GHCR/Quay give no annual totals | Snapshot lifetime counters daily and diff them (history builds up) |
| CI runs / test history (Jenkins) | Not related to user activity; Jenkins history is separate | Actions API run counts if wanted |
| GitHub traffic beyond 14 days | GitHub only keeps 14 days | Already accumulating in `github_traffic` from first run on |
| Reconciliation of old report figures (247/364 PRs, 1,174 commits, 24,357 "runs") | Old method/scope unknown; "runs" were WebApp pageviews | Documented in the KPI evidence workbook; not reproduced |

## Caveats shown on the page

- Repo-wide activity includes the wider community, not only funded work.
- A repo can count towards several services (OpenMS/OpenMS → Core and Python): don't add service rows.
- Downloads are download events (CI, mirrors and dependency installs included), not users.
