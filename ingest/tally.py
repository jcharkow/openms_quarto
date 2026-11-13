#!/usr/bin/env python3
"""
Pull survey submissions from the Tally API (or a CSV export) into tidy parquet.

    python -m ingest.tally                 # API: needs TALLY_API_KEY, TALLY_FORM_ID
    python -m ingest.tally --csv export.csv
    python -m ingest.tally --dump-raw raw.json   # also save the raw API response for debugging

Writes data/survey_respondents.parquet and data/survey_choices.parquet.
Names and emails are dropped here (email becomes a hash), so they never reach the dashboard.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import pandas as pd
import requests

from ingest.common import (COL_ID, COL_RESPONDENT, COL_SUBMITTED, MULTI_SELECT, require_env,
                           tidy_survey, write_table)

API = "https://api.tally.so"
UNTITLED = "Untitled checkboxes field"


def fetch_submissions(api_key: str, form_id: str) -> tuple[list[dict], list[dict]]:
    """All completed submissions plus the question list."""
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {api_key}"
    page, questions, subs = 1, [], []
    while True:
        r = s.get(f"{API}/forms/{form_id}/submissions",
                  params={"page": page, "limit": 500, "filter": "completed"}, timeout=60)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 5)))
            continue
        r.raise_for_status()
        body = r.json()
        questions = body.get("questions") or questions
        subs += body.get("submissions", [])
        if not body.get("hasMore"):
            return questions, subs
        page += 1


def _label(item, field_titles: dict) -> str:
    """An answer element may be a plain label, an option id, or an object."""
    if isinstance(item, dict):
        item = item.get("text") or item.get("label") or item.get("title") or item.get("value") or item.get("id")
    item = str(item)
    return field_titles.get(item, item)


def to_export_frame(questions: list[dict], subs: list[dict]) -> pd.DataFrame:
    """Reshape API JSON into the same columns as Tally's CSV export."""
    qinfo = {}
    for q in questions:
        title = (q.get("title") or "").strip() or UNTITLED
        fields = {f.get("uuid"): (f.get("title") or "").strip() for f in q.get("fields") or []}
        qinfo[q["id"]] = (title, fields)

    rows = []
    for sub in subs:
        responses = sub.get("responses") or []
        row = {
            COL_ID: sub.get("id"),
            COL_SUBMITTED: sub.get("submittedAt"),
            COL_RESPONDENT: responses[0].get("respondentId") if responses else None,
        }
        for resp in responses:
            title, fields = qinfo.get(resp.get("questionId"), (resp.get("questionId"), {}))
            ans = resp.get("answer")
            if ans is None:
                continue
            if isinstance(ans, list):
                labels = [_label(a, fields) for a in ans]
                if title in MULTI_SELECT or title == UNTITLED:
                    for lab in labels:
                        row[f"{title} ({lab})"] = True
                else:  # single choice delivered as a one-element list
                    row[title] = ", ".join(labels)
            elif isinstance(ans, dict):
                row[title] = resp.get("formattedAnswer") or json.dumps(ans)
            else:
                row[title] = ans
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", help="Use a Tally CSV export instead of the API")
    ap.add_argument("--dump-raw", help="Save the raw API response here (contains personal data!)")
    args = ap.parse_args()

    print("Tally survey")
    if args.csv:
        df = pd.read_csv(args.csv)
    else:
        questions, subs = fetch_submissions(require_env("TALLY_API_KEY"), require_env("TALLY_FORM_ID"))
        if args.dump_raw:
            with open(args.dump_raw, "w") as f:
                json.dump({"questions": questions, "submissions": subs}, f, indent=1)
            os.chmod(args.dump_raw, 0o600)
        df = to_export_frame(questions, subs)

    respondents, choices = tidy_survey(df)
    write_table(respondents, "survey_respondents")
    write_table(choices, "survey_choices")


if __name__ == "__main__":
    main()
