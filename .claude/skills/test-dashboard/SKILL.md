---
name: test-dashboard
description: Render the OpenMS Quarto dashboard offline with fake data and check every page. Use after any change to dashboard/index.qmd, ingest/common.py or table schemas, or when asked to test, preview or verify the dashboard.
---

# Test the dashboard with fake data

Never use the real `data/` directory for this.

1. Pick a scratch dir and Python that has `requirements.txt` installed (a `.venv`, or create one
   with `uv venv && uv pip install -r requirements.txt`). Quarto must be on PATH or downloaded
   (https://github.com/quarto-dev/quarto-cli/releases, linux-amd64 tarball works without root).

2. Generate fake data and render:

   ```bash
   export OPENMS_DATA_DIR=<scratch>/data
   python scripts/make_fake_data.py
   (cd dashboard && QUARTO_PYTHON=$(realpath -s <python>) quarto render index.qmd)
   python scripts/check_render.py dashboard/index.html --strict
   ```

   A failed cell makes `quarto render` exit non-zero and prints the traceback — read it, fix, rerun.

3. Check the output of `check_render.py`:
   - every value box has a plausible number (not `–`, which means the table was missing);
   - with full fake data there should be **no** "No … data yet" placeholders;
   - if you added a table, extend `scripts/make_fake_data.py` so it gets fake rows too.

4. Also test the "nothing ingested yet" case: render once with an empty `OPENMS_DATA_DIR`
   — every card must show a placeholder, not crash.

5. Run the unit tests too: `python -m pytest tests` (install `requirements-dev.txt`).
   CI runs the same steps on every PR (`.github/workflows/test.yml`).

6. Clean up: `rm -rf dashboard/index.html dashboard/index_files dashboard/.quarto`.

Layout can't be checked from HTML alone. If a browser isn't available, tell the user to run
`cd dashboard && quarto preview index.qmd` and look at it.
