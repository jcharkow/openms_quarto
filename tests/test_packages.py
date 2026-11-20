import pandas as pd
import pytest

import ingest.packages as p
from ingest.common import kpi_periods, parse_mapping, read_table


def test_parse_mapping():
    m = parse_mapping(" OpenMS/OpenMS=core|python, bigbio/quantms=Workflows ,OpenMS/x,")
    assert m == {"OpenMS/OpenMS": ["core", "python"], "bigbio/quantms": ["workflows"], "OpenMS/x": []}
    with pytest.raises(SystemExit):
        parse_mapping("a/b=nope")


def test_kpi_periods_roll_with_the_year():
    labels = [p[0] for p in kpi_periods(pd.Timestamp("2026-11-20"))]
    assert labels == ["2023", "2024", "2025", "2026 YTD"]
    last = kpi_periods(pd.Timestamp("2027-02-01"))
    assert [x[0] for x in last] == ["2024", "2025", "2026", "2027 YTD"]
    assert last[-1][2] == pd.Timestamp("2027-02-02")      # end is exclusive, today included


def test_packages_incremental(data_dir, monkeypatch):
    monkeypatch.setenv("PACKAGES_SINCE", "2026-08-01")
    monkeypatch.setenv("BIOCONDA_PACKAGES", "openms=core,pyopenms=python")
    monkeypatch.setenv("PYPI_PACKAGES", "pyopenms=python")
    monkeypatch.setattr(p.pd.Timestamp, "now", classmethod(lambda cls: pd.Timestamp("2026-11-20")))
    fetched = []

    def conda(month, pkgs):
        fetched.append(month)
        if month >= pd.Timestamp("2026-10-01"):
            return None                                   # not published yet
        return pd.DataFrame({"channel": "bioconda", "package": pkgs, "month": month, "downloads": 5})

    pypi_calls = [pd.DataFrame({"channel": "pypi", "package": ["pyopenms"],
                                "month": [pd.Timestamp("2026-11-01")], "downloads": [10]}),
                  pd.DataFrame({"channel": "pypi", "package": ["pyopenms"],
                                "month": [pd.Timestamp("2026-11-01")], "downloads": [25]})]
    monkeypatch.setattr(p, "fetch_conda_month", conda)
    monkeypatch.setattr(p, "fetch_pypi", lambda pkgs, since: pypi_calls.pop(0))

    p.main()
    d = read_table("package_downloads")
    assert len(d[d.channel == "bioconda"]) == 4            # Aug + Sep x 2 packages
    assert fetched == [pd.Timestamp(m) for m in ("2026-08-01", "2026-09-01", "2026-10-01")]

    fetched.clear()
    p.main()
    assert fetched == [pd.Timestamp("2026-10-01")]         # stored months are skipped
    d = read_table("package_downloads")
    assert d[d.channel == "pypi"].downloads.tolist() == [25]  # current month updated, not duplicated
    assert set(read_table("package_services").service) == {"core", "python"}
