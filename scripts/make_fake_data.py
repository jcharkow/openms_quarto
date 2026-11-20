#!/usr/bin/env python3
"""
Write fake data for every table so the dashboard can be rendered and checked offline.

    OPENMS_DATA_DIR=/tmp/x python scripts/make_fake_data.py   # also writes /tmp/x/fake_survey.csv

Never point this at the real data/ directory: it overwrites the tables.
"""
import os
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ingest.common import DATA_DIR, ROOT, tidy_survey, write_table  # noqa: E402

if DATA_DIR.resolve() == (ROOT / "data").resolve() and "--force" not in sys.argv:
    raise SystemExit("Refusing to overwrite real data/. Set OPENMS_DATA_DIR to a scratch directory.")

random.seed(1)
rng = np.random.default_rng(0)
DATA_DIR.mkdir(parents=True, exist_ok=True)
now = pd.Timestamp.now().normalize()

# --- survey (Tally CSV export layout) --------------------------------------
roles = ["PhD Student", "Postdoc", "Software Developer", "Core Facility Staff", "PI / Group Leader"]
interests = ["Proteomics", "Metabolomics", "DIA", "Workflows", "Python (pyOpenMS)"]
platforms = ["Windows", "Mac", "Linux", "KNIME", "Galaxy", "Nextflow"]
affils = ["Uni Tübingen", "University of Tübingen", "ETH Zurich", "eth zurich", "EMBL", "MIT", "M.I.T"]
rows = []
for i in range(120):
    r = {"Submission ID": f"s{i}", "Respondent ID": f"r{i}",
         "Submitted at": (now - pd.Timedelta(days=random.randint(0, 250))).isoformat(),
         "Name": f"Person {i}", "Email": f"p{i % 110}@example.org", "Affiliation": random.choice(affils),
         "Please Select the Option that Best Describes Your Role": random.choice(roles),
         "GitHub Handle": random.choice(["", "", f"https://github.com/dev{i % 15}", f"@dev{i % 15}"]),
         "Discord Handle": random.choice(["", "helper#1234", "@dev", f"user{i}"]),
         "Additional Feedback": random.choice(["", "Great tool!", "More docs, please"]),
         "Untitled checkboxes field (Please Reach Out to Me via Email)": random.random() < .4,
         "Untitled checkboxes field (Sign Me Up for the OpenMS Newsletter)": random.random() < .5}
    for o in interests:
        r[f"Please Select Your Areas of Interest ({o})"] = random.random() < .4
    for o in platforms:
        r[f"Which Platform(s) do you use/plan to use OpenMS on ({o})"] = random.random() < .35
    rows.append(r)
survey = pd.DataFrame(rows)
survey.to_csv(DATA_DIR / "fake_survey.csv", index=False)
resp, choices = tidy_survey(survey)
write_table(resp, "survey_respondents")
write_table(choices, "survey_choices")

# --- GitHub -----------------------------------------------------------------
repo = "OpenMS/OpenMS"
authors = [f"dev{i}" for i in range(30)]
created = now - pd.to_timedelta(rng.integers(0, 1000, 600), unit="D")
is_pr = rng.random(600) < .5
closed = [c + pd.Timedelta(days=int(rng.integers(1, 60))) if rng.random() < .8 else pd.NaT for c in created]
write_table(pd.DataFrame({
    "repo": repo, "number": range(1, 601), "is_pr": is_pr, "author": rng.choice(authors, 600),
    "author_association": "CONTRIBUTOR", "is_bot": False,
    "state": ["closed" if pd.notna(c) else "open" for c in closed], "title": "fake",
    "created_at": created, "closed_at": closed,
    "merged_at": [c if p and pd.notna(c) else pd.NaT for c, p in zip(closed, is_pr)],
    "updated_at": created, "comments": 0}), "github_issues")
write_table(pd.DataFrame({"repo": repo, "user": [f"u{i}" for i in range(300)] + authors[:10],
                          "starred_at": now - pd.to_timedelta(np.sort(rng.integers(0, 2000, 310))[::-1], unit="D")}),
            "github_stars")
write_table(pd.DataFrame({"repo": repo, "login": authors, "contributions": rng.integers(1, 500, 30),
                          "is_bot": False}), "github_contributors")
write_table(pd.DataFrame({"repo": repo, "tag": [f"Release3.{i}.0" for i in range(5)],
                          "published_at": [now - pd.Timedelta(days=300 - 60 * i) for i in range(5)],
                          "prerelease": False, "asset": "installer", "downloads": rng.integers(100, 3000, 5)}),
            "github_releases")
write_table(pd.DataFrame({"date": [now], "repo": repo, "stars": 310, "forks": 300, "watchers": 40,
                          "open_issues_and_prs": 130}), "github_daily")
days = pd.date_range(now - pd.Timedelta(days=13), now)
write_table(pd.concat([pd.DataFrame({"repo": repo, "date": days, "kind": k,
                                     "count": rng.integers(50, 300, 14), "uniques": rng.integers(10, 80, 14)})
                       for k in ("views", "clones")]), "github_traffic")

# --- Funder KPIs: commits, discussions, service mapping, package downloads ----
write_table(pd.DataFrame({"repo": [repo, repo, "OpenMS/pyopenms_viz", "bigbio/quantms"],
                          "service": ["core", "python", "python", "workflows"]}), "github_repo_services")
n = 2000
c_repo = rng.choice([repo, repo, repo, "OpenMS/pyopenms_viz", "bigbio/quantms"], n)
c_at = now - pd.to_timedelta(rng.integers(0, 1400, n), unit="D")
write_table(pd.DataFrame({"repo": c_repo, "sha": [f"{i:040x}" for i in range(n)],
                          "author": rng.choice(authors + [None, "dependabot[bot]"], n),
                          "is_bot": False, "authored_at": c_at, "committed_at": c_at,
                          "is_merge": rng.random(n) < .2}).assign(
                              is_bot=lambda d: d.author.fillna("").str.endswith("[bot]")), "github_commits")
write_table(pd.DataFrame({"repo": rng.choice([repo, "bigbio/quantms"], 40), "number": range(1, 41),
                          "created_at": now - pd.to_timedelta(rng.integers(0, 1400, 40), unit="D"),
                          "author": rng.choice(authors, 40), "is_bot": False, "category": "Q&A",
                          "answered_at": pd.NaT}), "github_discussions")
months = pd.date_range(f"{now.year - 3}-01-01", now - pd.offsets.MonthBegin(1), freq="MS")
pkgs = [("bioconda", "libopenms", "core"), ("bioconda", "openms", "core"), ("bioconda", "pyopenms", "python"),
        ("pypi", "pyopenms", "python"), ("pypi", "pyopenms-viz", "python")]
write_table(pd.concat([pd.DataFrame({"channel": ch, "package": p, "month": months,
                                     "downloads": rng.integers(300, 900, len(months)) * (100 if ch == "pypi" else 1)})
                       for ch, p, _ in pkgs]), "package_downloads")
write_table(pd.DataFrame(pkgs, columns=["channel", "package", "service"]), "package_services")

# --- Discord ----------------------------------------------------------------
days = pd.date_range(now - pd.Timedelta(days=40), now)
write_table(pd.DataFrame({"date": days, "members": np.arange(len(days)) + 800,
                          "online": 60 + np.arange(len(days)) % 9}), "discord_daily")
names = [f"member{i}" for i in range(840)]
names[:2] = ["helper", "dev"]
names[2:40] = [f"user{i}" for i in range(38)]
left = [now - pd.Timedelta(days=5) if i >= 835 else pd.NaT for i in range(840)]
write_table(pd.DataFrame({
    "user_id": [str(i) for i in range(840)], "username": names, "global_name": None, "nick": None,
    "is_bot": False, "joined_at": now - pd.to_timedelta(np.sort(rng.integers(0, 1500, 840))[::-1], unit="D"),
    "last_seen": now, "left_seen": left, "first_seen": now - pd.Timedelta(days=40)}), "discord_members")
write_table(pd.DataFrame({
    "channel_id": "1", "channel": rng.choice(["general", "help"], 800), "message_id": np.arange(800, dtype="int64"),
    "author": rng.choice(["helper", "dev", "user3", "user7"], 800), "author_is_bot": False,
    "created_at": now - pd.to_timedelta(rng.integers(0, 150 * 24, 800), unit="h")}), "discord_messages")
print(f"Fake data written to {DATA_DIR}")
