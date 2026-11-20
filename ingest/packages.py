#!/usr/bin/env python3
"""
Monthly package downloads from Bioconda and PyPI into parquet.

    python -m ingest.packages

Sources (public, no credentials; only package names are sent):
  Bioconda  Anaconda's public package data: one parquet per month at
            https://anaconda-package-data.s3.amazonaws.com/conda/monthly/YYYY/YYYY-MM.parquet
            (~10 MB each; published after the month ends)
  PyPI      ClickPy's public ClickHouse mirror of the PyPI download logs (pypi_downloads_per_day)

Env (same `name=service|service` syntax as GITHUB_REPOS):
  BIOCONDA_PACKAGES     default "libopenms=core,openms=core,openms-thirdparty=core,pyopenms=python"
  PYPI_PACKAGES         default "pyopenms=python,pyopenms-viz=python"
  PACKAGES_SINCE        first month to backfill, default 1 January three years ago
  CLICKPY_URL           default https://sql-clickhouse.clickhouse.com/?user=play

Tables:
  package_downloads   channel, package, month, downloads (all versions / platforms; includes CI and
                      dependency downloads, so not unique users). Months already stored are not re-fetched
                      for Bioconda; PyPI is re-queried each run (the current month keeps growing).
  package_services    channel, package, service
"""
from __future__ import annotations

import io
import os
import re

import pandas as pd
import pyarrow.parquet as pq
import requests

from ingest.common import parse_mapping, read_table, write_table

CONDA_URL = "https://anaconda-package-data.s3.amazonaws.com/conda/monthly/{y}/{y}-{m:02d}.parquet"
CLICKPY_URL = "https://sql-clickhouse.clickhouse.com/?user=play"
NAME_OK = re.compile(r"^[A-Za-z0-9._-]+$")


def fetch_conda_month(month: pd.Timestamp, packages: list[str]) -> pd.DataFrame | None:
    """Bioconda downloads per package for one month; None if the month isn't published yet."""
    r = requests.get(CONDA_URL.format(y=month.year, m=month.month), timeout=300)
    if r.status_code in (403, 404):
        return None
    r.raise_for_status()
    t = pq.read_table(io.BytesIO(r.content), columns=["data_source", "pkg_name", "counts"],
                      filters=[("pkg_name", "in", packages)]).to_pandas()
    t = t[t.data_source.astype(str) == "bioconda"]
    got = t.groupby(t.pkg_name.astype(str)).counts.sum()
    # one row per requested package, also for zero downloads, so the month counts as fetched
    return pd.DataFrame({"channel": "bioconda", "package": packages, "month": month,
                         "downloads": [int(got.get(p, 0)) for p in packages]})


def fetch_pypi(packages: list[str], since: pd.Timestamp) -> pd.DataFrame:
    for p in packages:
        if not NAME_OK.match(p):
            raise SystemExit(f"Invalid PyPI package name {p!r}")
    names = ",".join(f"'{p}'" for p in packages)
    sql = (f"SELECT project, toStartOfMonth(date) AS month, sum(count) AS downloads "
           f"FROM pypi.pypi_downloads_per_day WHERE project IN ({names}) "
           f"AND date >= '{since:%Y-%m-%d}' GROUP BY project, month ORDER BY month FORMAT TSV")
    r = requests.post(os.environ.get("CLICKPY_URL", CLICKPY_URL), data=sql.encode(), timeout=120)
    r.raise_for_status()
    rows = [line.split("\t") for line in r.text.splitlines() if line.strip()]
    return pd.DataFrame({"channel": "pypi", "package": [x[0] for x in rows],
                         "month": pd.to_datetime([x[1] for x in rows]),
                         "downloads": [int(x[2]) for x in rows]})


def main():
    today = pd.Timestamp.now().normalize()
    since = pd.Timestamp(os.environ.get("PACKAGES_SINCE") or f"{today.year - 3}-01-01").to_period("M").to_timestamp()
    conda = parse_mapping(os.environ.get("BIOCONDA_PACKAGES",
                                         "libopenms=core,openms=core,openms-thirdparty=core,pyopenms=python"))
    pypi = parse_mapping(os.environ.get("PYPI_PACKAGES", "pyopenms=python,pyopenms-viz=python"))

    old = read_table("package_downloads")
    frames = [] if old is None else [old]
    failed = False

    if conda:
        pkgs = list(conda)
        have = set()
        if old is not None and not old.empty:
            o = old[old.channel == "bioconda"]
            # a month is complete if every requested package has a row
            full = o.groupby("month").package.apply(lambda s: set(pkgs) <= set(s))
            have = set(full[full].index)
        last_full_month = (today.to_period("M") - 1).to_timestamp()
        for month in pd.date_range(since, last_full_month, freq="MS"):
            if month in have:
                continue
            print(f"  bioconda {month:%Y-%m}")
            try:
                df = fetch_conda_month(month, pkgs)
            except requests.RequestException as e:
                print(f"  bioconda {month:%Y-%m} failed: {e}")
                failed = True
                continue
            if df is None:
                print(f"  bioconda {month:%Y-%m} not published yet")
                break
            frames.append(df)

    if pypi:
        try:
            frames.append(fetch_pypi(list(pypi), since))
        except requests.RequestException as e:
            print(f"  PyPI (ClickPy) failed: {e}")
            failed = True

    if frames:
        out = pd.concat(frames).drop_duplicates(["channel", "package", "month"], keep="last")
        write_table(out.sort_values(["channel", "package", "month"]).reset_index(drop=True), "package_downloads")
    write_table(pd.DataFrame([{"channel": ch, "package": p, "service": s}
                              for ch, m in (("bioconda", conda), ("pypi", pypi))
                              for p, svcs in m.items() for s in svcs],
                             columns=["channel", "package", "service"]), "package_services")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
