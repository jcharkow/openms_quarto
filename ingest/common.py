"""Shared helpers: survey column names, cleaning, and parquet I/O.

Used by the ingest scripts, the Quarto dashboard and openms_survey_report.py.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("OPENMS_DATA_DIR", ROOT / "data"))

# --------------------------------------------------------------------------- #
# Survey column names (as exported by Tally)
# --------------------------------------------------------------------------- #
COL_SUBMITTED = "Submitted at"
COL_ID = "Submission ID"
COL_RESPONDENT = "Respondent ID"
COL_NAME = "Name"
COL_EMAIL = "Email"
COL_AFFIL = "Affiliation"
COL_ROLE = "Please Select the Option that Best Describes Your Role"
COL_INTEREST = "Please Select Your Areas of Interest"
COL_PLATFORM = "Which Platform(s) do you use/plan to use OpenMS on"
COL_GITHUB = "GitHub Handle"
COL_DISCORD = "Discord Handle"
COL_FEEDBACK = "Additional Feedback"
COL_REACH_EMAIL = "Untitled checkboxes field (Please Reach Out to Me via Email)"
COL_NEWSLETTER = "Untitled checkboxes field (Sign Me Up for the OpenMS Newsletter)"

# Multi-select questions -> short key used in the tidy "choices" table
MULTI_SELECT = {COL_INTEREST: "interest", COL_PLATFORM: "platform"}

FALSY = {"", "false", "0", "no", "nan", "none", "unchecked", "off"}


# --------------------------------------------------------------------------- #
# Cleaning helpers
# --------------------------------------------------------------------------- #
def is_selected(series: pd.Series) -> pd.Series:
    """True where a checkbox-style cell counts as ticked (True/'true'/label...)."""
    return ~series.fillna("").astype(str).str.strip().str.lower().isin(FALSY)


def option_label(col: str, prefix: str) -> str:
    """'Prefix (Label)' -> 'Label'."""
    return re.sub(rf"^{re.escape(prefix)}\s*\(", "", col).rstrip(") ").strip()


def multi_select_counts(df: pd.DataFrame, prefix: str) -> pd.Series:
    """
    Count selections for a multi-select question.
    Uses the one-column-per-option layout ('prefix (Option)') when present,
    otherwise falls back to splitting the parent comma-separated column.
    """
    sub_cols = [c for c in df.columns if c.startswith(prefix + " (")]
    if sub_cols:
        counts = {option_label(c, prefix): int(is_selected(df[c]).sum()) for c in sub_cols}
        return pd.Series(counts).sort_values(ascending=False)

    if prefix in df.columns:
        exploded = df[prefix].dropna().astype(str).str.split(r"\s*,\s*").explode().str.strip()
        exploded = exploded[exploded != ""]
        return exploded.value_counts()
    return pd.Series(dtype=int)


def value_counts_clean(series: pd.Series, top: int | None = None) -> pd.Series:
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    vc = s.value_counts()
    return vc.head(top) if top else vc


def _affil_key(s: pd.Series) -> pd.Series:
    return (s.str.lower().str.replace(r"[^\w\s]", "", regex=True)
            .str.replace(r"\s+", " ", regex=True).str.strip())


def normalise_affiliation(series: pd.Series) -> pd.Series:
    """Counts per affiliation so 'MIT', 'mit ' and 'M.I.T' group together."""
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    key = _affil_key(s)
    # Keep the most common original spelling for each key
    display = s.groupby(key).agg(lambda x: x.value_counts().index[0])
    counts = key.value_counts()
    counts.index = [display[k] for k in counts.index]
    return counts


def affiliation_display(series: pd.Series) -> pd.Series:
    """Row-wise version of normalise_affiliation: each value -> canonical spelling."""
    s = series.fillna("").astype(str).str.strip()
    key = _affil_key(s)
    nonempty = s != ""
    display = s[nonempty].groupby(key[nonempty]).agg(lambda x: x.value_counts().index[0])
    return key.map(display).where(nonempty)


def clean_github_handle(v) -> str | None:
    """'https://github.com/Foo/', '@Foo', ' foo ' -> 'foo'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    s = re.sub(r"^(https?://)?(www\.)?github\.com/", "", s, flags=re.I)
    s = s.strip("/@ ").split("/")[0].lower()
    return s or None


def clean_discord_handle(v) -> str | None:
    """'@Foo', 'Foo#1234', 'foo#0' -> 'foo'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().lstrip("@").split("#")[0].strip().lower()
    return s or None


def email_hash(v) -> str | None:
    """Stable pseudonym for counting unique emails without storing them."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or not str(v).strip():
        return None
    return hashlib.sha256(str(v).strip().lower().encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Tidy survey tables
# --------------------------------------------------------------------------- #
def tidy_survey(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Turn a Tally export-shaped frame into two tidy tables:

    respondents: one row per submission. Names and emails are NOT kept
                 (email is replaced by a hash so unique people can be counted).
    choices:     one row per (submission, multi-select question, option).
    """
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    if COL_ID in df.columns:
        df = df.drop_duplicates(subset=COL_ID)
    df = df.reset_index(drop=True)
    if COL_ID not in df.columns:
        df[COL_ID] = [f"row{i}" for i in range(len(df))]

    def col(name):
        return df[name] if name in df.columns else pd.Series([None] * len(df), index=df.index)

    def text(name):
        s = col(name).astype("string").str.strip()
        return s.where(s != "")

    submitted = pd.to_datetime(col(COL_SUBMITTED), errors="coerce", utc=True).dt.tz_localize(None)

    resp = pd.DataFrame({
        "submission_id": df[COL_ID].astype(str),
        "respondent_id": text(COL_RESPONDENT),
        "submitted_at": submitted,
        "email_hash": col(COL_EMAIL).map(email_hash),
        "affiliation": text(COL_AFFIL),
        "affiliation_norm": affiliation_display(col(COL_AFFIL)),
        "role": text(COL_ROLE),
        "github_handle": col(COL_GITHUB).map(clean_github_handle),
        "discord_handle": col(COL_DISCORD).map(clean_discord_handle),
        "feedback": text(COL_FEEDBACK),
        "newsletter": is_selected(col(COL_NEWSLETTER)) if COL_NEWSLETTER in df.columns else False,
        "reach_email": is_selected(col(COL_REACH_EMAIL)) if COL_REACH_EMAIL in df.columns else False,
        "has_name": text(COL_NAME).notna(),
    })

    rows = []
    for prefix, key in MULTI_SELECT.items():
        sub_cols = [c for c in df.columns if c.startswith(prefix + " (")]
        if sub_cols:
            for c in sub_cols:
                sel = is_selected(df[c])
                for sid in df.loc[sel, COL_ID].astype(str):
                    rows.append((sid, key, option_label(c, prefix)))
        elif prefix in df.columns:
            for sid, val in zip(df[COL_ID].astype(str), df[prefix]):
                if pd.isna(val):
                    continue
                for opt in re.split(r"\s*,\s*", str(val)):
                    if opt.strip():
                        rows.append((sid, key, opt.strip()))
    choices = pd.DataFrame(rows, columns=["submission_id", "question", "option"])
    return resp, choices


# --------------------------------------------------------------------------- #
# Parquet I/O
# --------------------------------------------------------------------------- #
def write_table(df: pd.DataFrame, name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{name}.parquet"
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)  # atomic: the dashboard never sees a half-written file
    print(f"  wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} ({len(df)} rows)")
    return path


def read_table(name: str) -> pd.DataFrame | None:
    path = DATA_DIR / f"{name}.parquet"
    return pd.read_parquet(path) if path.exists() else None


def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Missing environment variable {name} (see .env.example)")
    return v
