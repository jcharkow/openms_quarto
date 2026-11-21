#!/usr/bin/env python3
"""
Check what GITHUB_TOKEN can do. Never prints the token itself.

    ./docker-refresh.sh python scripts/check_github_token.py      # Docker
    set -a; . ./.env; set +a; .venv/bin/python scripts/check_github_token.py   # without Docker

Optional: a repo to test against (default: the first repo in GITHUB_REPOS, else OpenMS/OpenMS).
"""
import os
import sys

import requests

API = "https://api.github.com"


def main():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repos = [r.split("=")[0].strip() for r in os.environ.get("GITHUB_REPOS", "").split(",") if r.strip()]
    repo = sys.argv[1] if len(sys.argv) > 1 else (repos[0] if repos else "OpenMS/OpenMS")

    print(f"token: {'set, ' + str(len(token)) + ' characters' if token else 'NOT SET'}"
          f"{' (starts like a fine-grained token)' if token.startswith('github_pat_') else ''}"
          f"{' (starts like a classic token)' if token.startswith('ghp_') else ''}")
    if not token:
        print("-> GITHUB_TOKEN is empty in the container. Check the line in .env: `GITHUB_TOKEN=...`,\n"
              "   not commented out, no leading spaces, no space after '='. Run via ./docker-refresh.sh.")
        return 1

    h = {"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"}

    def check(label, url, accept=None, method="GET", json=None):
        hdr = {**h, **({"Accept": accept} if accept else {})}
        r = requests.request(method, API + url, headers=hdr, json=json, timeout=30)
        try:
            body = r.json()
        except ValueError:
            body = {}
        msg = body.get("message", "") if isinstance(body, dict) else ""
        print(f"{label:<28} HTTP {r.status_code} {msg}")
        return r, body

    r, body = check("rate limit", "/rate_limit")
    if r.status_code == 401:
        print("-> GitHub rejects the token (wrong, expired or revoked). Create a new one.")
        return 1
    print(f"{'':<28} limit {body.get('rate', {}).get('limit')} / hour "
          f"(5000 = token accepted, 60 = treated as anonymous)")

    check("user", "/user")
    r_repo, _ = check(f"repo {repo}", f"/repos/{repo}")
    r_star, _ = check("stargazers", f"/repos/{repo}/stargazers?per_page=1",
                      accept="application/vnd.github.star+json")
    check("commits", f"/repos/{repo}/commits?per_page=1")
    owner, name = repo.split("/", 1)
    r_gql, gql = check("discussions (GraphQL)", "/graphql", method="POST",
                       json={"query": "query($o:String!,$n:String!){repository(owner:$o,name:$n)"
                                      "{hasDiscussionsEnabled}}", "variables": {"o": owner, "n": name}})
    if gql.get("errors"):
        print(f"{'':<28} GraphQL error: {gql['errors'][0].get('message')}")
    r_traffic, _ = check("traffic (optional)", f"/repos/{repo}/traffic/views")

    print()
    if r_repo.ok and r_star.ok and r_gql.ok and not gql.get("errors"):
        print("-> Token works for everything the dashboard needs.")
    elif r_star.status_code in (401, 403) or r_repo.status_code == 404:
        print("-> Token is valid but can't read this repo. Fine-grained token: set Repository access to\n"
              "   'Public repositories' (or 'All repositories'). Or use a classic token with no scopes ticked.")
    else:
        print("-> Unexpected result; send this output.")
    if r_traffic.status_code in (401, 403, 404):
        print("   Traffic is optional: it needs write access to the repo (see README).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
