---
name: add-data-source
description: Add a new metrics source (e.g. LinkedIn page exports, YouTube, PyPI downloads, mailing list) to the OpenMS dashboard — ingest script, tables, dashboard page, docs. Use when the user wants to track a new platform or metric.
---

# Add a data source

Read AGENTS.md first (privacy rules, history rules, conventions).

1. **Decide how the data arrives** and confirm with the user if unclear:
   - API with a token → `ingest/<source>.py`, secrets via `require_env` + `.env.example`.
   - Manual export (e.g. LinkedIn page analytics .xls/.csv) → script reads every file in
     `data/inbox/<source>/` and merges them; ask the user for a real export file to build the
     parser from — do not guess column names.
   - Avoid routing data through third-party services (see AGENTS.md).

2. **Write the ingest module** following `ingest/github.py` / `ingest/discord_snapshot.py`:
   - `main()` + `if __name__ == "__main__": main()`; runnable as `python -m ingest.<source>`.
   - Write with `write_table(df, "<source>_<thing>")`; table names are prefixed by source.
   - Anything that accumulates over time must merge with the existing table
     (`read_table` + concat + `drop_duplicates(keys, keep="last")`), never replace it.
   - Handle missing permissions/tokens by printing a hint and skipping, not crashing.
   - No PII beyond handles that are needed for matching; no message/post content unless asked.

3. **Register it**: add `ingest.<source>` to the loop in `refresh.sh`, env vars to `.env.example`,
   a row to the layout tables in README.md and AGENTS.md, setup steps to README "Tokens".

4. **Dashboard**: add a `# <Source>` page to `dashboard/index.qmd` — load with `read_table` in the
   setup cell, a value-box row, then chart rows. Every cell must handle the table being `None`
   (`none_msg`). Add to the "Data freshness" table on the Overview page.

5. **Fake data**: extend `scripts/make_fake_data.py` with realistic fake rows for the new tables.

6. **Test**: mock the client and run `main()` twice against a scratch `OPENMS_DATA_DIR` (checks
   incremental merge + de-dup), then run the `test-dashboard` skill.
