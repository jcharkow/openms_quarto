#!/usr/bin/env python3
"""
Pull GitHub metrics into parquet.

    python -m ingest.github      # GITHUB_TOKEN (recommended), GITHUB_REPOS (see below)

GITHUB_REPOS is a comma-separated list; each repo can name the service packages it counts towards
for the funder KPIs (core, python, webapps, workflows), e.g.
    GITHUB_REPOS="OpenMS/OpenMS=core|python, OpenMS/pyopenms_viz=python, bigbio/quantms=workflows"

Tables (data/*.parquet):
  github_daily         one row per repo per day: stars, forks, watchers, open issues (history builds up;
                       the only star history: GitHub removed the stargazer list API on 2026-06-30)
  github_issues        issues + PRs (incremental via `since`)
  github_contributors  commit counts per contributor
  github_releases      release assets and download counts
  github_commits       default-branch commits (incremental; backfill from GITHUB_COMMITS_SINCE,
                       default 1 January three years ago)
  github_discussions   discussions (GraphQL, needs a token)
  github_repo_services repo -> service package mapping from GITHUB_REPOS
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from ingest.common import parse_mapping, read_table, write_table

API = "https://api.github.com"


class GitHub:
    def __init__(self, token: str | None):
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    def get(self, url, params=None, accept=None, optional=False):
        headers = {"Accept": accept} if accept else None
        while True:
            r = self.s.get(url if url.startswith("http") else API + url,
                           params=params, headers=headers, timeout=60)
            if r.status_code in (403, 429) and r.headers.get("X-RateLimit-Remaining") == "0":
                wait = max(5, int(r.headers.get("X-RateLimit-Reset", time.time() + 60)) - int(time.time()))
                print(f"  rate limited, sleeping {wait}s")
                time.sleep(min(wait, 3600))
                continue
            if optional and r.status_code in (401, 403, 404):
                try:
                    reason = r.json().get("message", "")
                except ValueError:
                    reason = ""
                self.last_skip = f"HTTP {r.status_code} {reason}".strip()
                return None  # e.g. no token / no push access
            if r.status_code == 202:  # stats being computed by GitHub
                time.sleep(3)
                continue
            r.raise_for_status()
            return r

    def paginate(self, url, params=None, accept=None, optional=False):
        params = {"per_page": 100, **(params or {})}
        pages, endpoint = 0, url.split("?")[0]
        while url:
            r = self.get(url, params, accept, optional)
            pages += 1
            if pages % 10 == 0:
                print(f"    ... {endpoint}: {pages} pages so far", flush=True)
            if r is None:
                why = getattr(self, "last_skip", "")
                session = getattr(self, "s", None)
                has_token = session is not None and "Authorization" in session.headers
                hint = ("token lacks access: fine-grained tokens need Repository access = Public repositories"
                        if has_token else "no GITHUB_TOKEN set")
                print(f"  skipped {url.split('?')[0]} ({why}; {hint})")
                return
            yield from r.json()
            url, params = r.links.get("next", {}).get("url"), None

    def graphql(self, query, variables):
        r = self.s.post(API + "/graphql", json={"query": query, "variables": variables}, timeout=60)
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(body["errors"])
        return body["data"]

    def discussions(self, repo):
        """All discussions of a repo, or None without a token (GraphQL needs auth)."""
        if "Authorization" not in self.s.headers:
            return None
        owner, name = repo.split("/", 1)
        out, cursor = [], None
        while True:
            d = self.graphql(DISCUSSIONS_QUERY, {"owner": owner, "name": name, "cursor": cursor})["repository"]
            if not d or not d["hasDiscussionsEnabled"]:
                return out
            page = d["discussions"]
            out += page["nodes"]
            if not page["pageInfo"]["hasNextPage"]:
                return out
            cursor = page["pageInfo"]["endCursor"]


DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    hasDiscussionsEnabled
    discussions(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes { number createdAt author { login __typename } category { name } answer { createdAt } }
    }
  }
}"""


def ts(v):
    return pd.to_datetime(v, utc=True).tz_localize(None) if v else pd.NaT


def upsert(name: str, new: pd.DataFrame, keys: list[str]):
    old = read_table(name)
    if old is not None and not old.empty:
        new = pd.concat([old, new]).drop_duplicates(subset=keys, keep="last")
    write_table(new.reset_index(drop=True), name)


def main():
    gh = GitHub(os.environ.get("GITHUB_TOKEN"))
    mapping = parse_mapping(os.environ.get("GITHUB_REPOS", "OpenMS/OpenMS=core|python"))
    repos = list(mapping)
    if not repos:
        print("GitHub: GITHUB_REPOS is empty, nothing to do")
        return
    today = datetime.now(timezone.utc).date()
    commits_since = pd.Timestamp(os.environ.get("GITHUB_COMMITS_SINCE") or f"{today.year - 3}-01-01")
    print(f"GitHub: {', '.join(repos)}")

    daily, contribs, releases, issues, commits, discussions = [], [], [], [], [], []
    old_issues = read_table("github_issues")
    old_commits = read_table("github_commits")

    for repo in repos:
        print(f"  {repo}", flush=True)
        info = gh.get(f"/repos/{repo}").json()
        daily.append({"date": pd.Timestamp(today), "repo": repo, "stars": info["stargazers_count"],
                      "forks": info["forks_count"], "watchers": info.get("subscribers_count"),
                      "open_issues_and_prs": info["open_issues_count"]})


        for c in gh.paginate(f"/repos/{repo}/contributors"):
            contribs.append({"repo": repo, "login": c["login"].lower(), "contributions": c["contributions"],
                             "is_bot": c.get("type") == "Bot"})

        for rel in gh.paginate(f"/repos/{repo}/releases"):
            for a in rel.get("assets") or [{"name": None, "download_count": 0}]:
                releases.append({"repo": repo, "tag": rel["tag_name"], "published_at": ts(rel.get("published_at")),
                                 "prerelease": rel["prerelease"], "asset": a["name"],
                                 "downloads": a["download_count"]})

        # Issues + PRs, incremental: only those updated since the last run
        since = None
        if old_issues is not None and not old_issues.empty:
            mine = old_issues[old_issues.repo == repo]
            if not mine.empty:
                since = (mine.updated_at.max() - pd.Timedelta(days=1)).isoformat() + "Z"
        params = {"state": "all", "sort": "updated", "direction": "asc", **({"since": since} if since else {})}
        print(f"    issues/PRs {'updated since ' + since[:10] if since else '(full history, first run: can take minutes)'}",
              flush=True)
        n0 = len(issues)
        for i in gh.paginate(f"/repos/{repo}/issues", params):
            pr = i.get("pull_request")
            issues.append({"repo": repo, "number": i["number"], "is_pr": pr is not None,
                           "author": (i.get("user") or {}).get("login", "").lower() or None,
                           "author_association": i.get("author_association"),
                           "is_bot": (i.get("user") or {}).get("type") == "Bot",
                           "state": i["state"], "title": i["title"],
                           "created_at": ts(i["created_at"]), "closed_at": ts(i.get("closed_at")),
                           "merged_at": ts(pr.get("merged_at")) if pr else pd.NaT,
                           "updated_at": ts(i["updated_at"]), "comments": i.get("comments", 0)})

        print(f"    {len(issues) - n0} issues/PRs", flush=True)

        # Default-branch commits, incremental (one day overlap; de-duplicated by sha)
        since = commits_since
        if old_commits is not None and not old_commits.empty:
            mine = old_commits[old_commits.repo == repo]
            if not mine.empty:
                since = max(since, mine.committed_at.max() - pd.Timedelta(days=1))
        print(f"    commits since {since:%Y-%m-%d}", flush=True)
        n0 = len(commits)
        for c in gh.paginate(f"/repos/{repo}/commits", {"since": since.isoformat() + "Z"}):
            author = c.get("author") or {}
            login = (author.get("login") or "").lower() or None
            commits.append({"repo": repo, "sha": c["sha"], "author": login,
                            "is_bot": author.get("type") == "Bot" or bool(login and login.endswith("[bot]")),
                            "authored_at": ts(c["commit"]["author"]["date"]),
                            "committed_at": ts(c["commit"]["committer"]["date"]),
                            "is_merge": len(c.get("parents") or []) > 1})

        print(f"    {len(commits) - n0} commits; discussions", flush=True)
        disc = gh.discussions(repo)
        if disc is None:
            print(f"  {repo}: no token, skipping discussions")
        for d in disc or []:
            author = d.get("author") or {}
            discussions.append({"repo": repo, "number": d["number"], "created_at": ts(d["createdAt"]),
                                "author": (author.get("login") or "").lower() or None,
                                "is_bot": author.get("__typename") == "Bot",
                                "category": (d.get("category") or {}).get("name"),
                                "answered_at": ts((d.get("answer") or {}).get("createdAt"))})

    upsert("github_daily", pd.DataFrame(daily), ["date", "repo"])
    # explicit columns: a repo without releases must still give a table the dashboard can filter
    write_table(pd.DataFrame(contribs, columns=["repo", "login", "contributions", "is_bot"]), "github_contributors")
    write_table(pd.DataFrame(releases, columns=["repo", "tag", "published_at", "prerelease", "asset", "downloads"]),
                "github_releases")
    if issues:
        upsert("github_issues", pd.DataFrame(issues), ["repo", "number"])
    if commits:
        upsert("github_commits", pd.DataFrame(commits), ["repo", "sha"])
    if discussions:
        upsert("github_discussions", pd.DataFrame(discussions), ["repo", "number"])
    write_table(pd.DataFrame([{"repo": r, "service": s} for r, svcs in mapping.items() for s in svcs],
                             columns=["repo", "service"]), "github_repo_services")


if __name__ == "__main__":
    main()
