#!/usr/bin/env python3
"""
Generate a PDF statistics report from an OpenMS sign-up / survey CSV export.

Usage:
    python openms_survey_report.py responses.csv [-o report.pdf] [--top 15]

Requires:  pip install pandas matplotlib reportlab
"""
import argparse
import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ingest.common import (  # shared with the ingest scripts and the dashboard
    COL_AFFIL, COL_DISCORD, COL_EMAIL, COL_FEEDBACK, COL_GITHUB, COL_ID, COL_INTEREST, COL_NAME,
    COL_NEWSLETTER, COL_PLATFORM, COL_REACH_EMAIL, COL_RESPONDENT, COL_ROLE, COL_SUBMITTED,
    is_selected, multi_select_counts, normalise_affiliation, option_label, value_counts_clean,
)

PRIMARY = colors.HexColor("#1F4E79")
LIGHT = colors.HexColor("#EAF1F8")
BAR_COLOR = "#2E75B6"


def fig_to_image(fig, width_cm=16) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = width_cm * cm
    img.drawHeight = width_cm * cm * ratio
    return img


def hbar_chart(counts: pd.Series, title: str, xlabel="Respondents") -> Image | None:
    if counts is None or counts.empty:
        return None
    counts = counts.iloc[::-1]  # largest at top
    height = max(2.2, 0.38 * len(counts) + 1.0)
    fig, ax = plt.subplots(figsize=(8, height))
    bars = ax.barh([str(i)[:55] for i in counts.index], counts.values, color=BAR_COLOR)
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
    ax.set_xlabel(xlabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.margins(x=0.12)
    return fig_to_image(fig)


def pie_chart(counts: pd.Series, title: str) -> Image | None:
    if counts is None or counts.empty:
        return None
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.pie(
        counts.values,
        labels=[str(i)[:30] for i in counts.index],
        autopct=lambda p: f"{p:.0f}%" if p >= 3 else "",
        startangle=90,
        wedgeprops={"edgecolor": "white"},
        textprops={"fontsize": 8},
    )
    ax.set_title(title, fontsize=11, fontweight="bold")
    return fig_to_image(fig, width_cm=11)


def timeline_chart(dates: pd.Series) -> Image | None:
    dates = dates.dropna()
    if dates.empty:
        return None
    span_days = (dates.max() - dates.min()).days
    freq = "D" if span_days <= 60 else ("W" if span_days <= 365 else "M")
    per = dates.dt.to_period(freq).value_counts().sort_index()
    full = pd.period_range(per.index.min(), per.index.max(), freq=freq)
    per = per.reindex(full, fill_value=0)

    fig, ax = plt.subplots(figsize=(8, 3.2))
    x = per.index.to_timestamp()
    ax.bar(x, per.values, width={"D": 0.8, "W": 5, "M": 25}[freq], color=BAR_COLOR, alpha=0.8)
    ax2 = ax.twinx()
    ax2.plot(x, per.cumsum().values, color="#C55A11", linewidth=2)
    ax2.set_ylabel("Cumulative", color="#C55A11")
    ax.set_ylabel({"D": "Per day", "W": "Per week", "M": "Per month"}[freq])
    ax.set_title("Submissions over time", fontsize=11, fontweight="bold", loc="left")
    ax.spines[["top"]].set_visible(False)
    ax2.spines[["top"]].set_visible(False)
    fig.autofmt_xdate()
    return fig_to_image(fig)


def heatmap_chart(matrix: pd.DataFrame, title: str) -> Image | None:
    if matrix.empty or matrix.values.sum() == 0:
        return None
    fig, ax = plt.subplots(
        figsize=(8, max(2.5, 0.45 * len(matrix) + 1.5)),
    )
    im = ax.imshow(matrix.values, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels([c[:22] for c in matrix.columns], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels([str(i)[:40] for i in matrix.index], fontsize=8)
    vmax = matrix.values.max()
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix.values[i, j]
            if v:
                ax.text(j, i, int(v), ha="center", va="center", fontsize=8,
                        color="white" if v > vmax * 0.6 else "black")
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    return fig_to_image(fig)


# --------------------------------------------------------------------------- #
# PDF building blocks
# --------------------------------------------------------------------------- #
def make_styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("ReportTitle", parent=ss["Title"], textColor=PRIMARY, fontSize=24, spaceAfter=6))
    ss.add(ParagraphStyle("Sub", parent=ss["Normal"], textColor=colors.grey, alignment=1, spaceAfter=18))
    ss.add(ParagraphStyle("H1", parent=ss["Heading1"], textColor=PRIMARY, spaceBefore=10, spaceAfter=6))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, leading=10))
    ss.add(ParagraphStyle("Quote", parent=ss["Normal"], fontSize=9, leading=12,
                          leftIndent=10, borderPadding=4, spaceAfter=6, textColor=colors.HexColor("#333333")))
    return ss


def kpi_table(items, styles):
    """items: list of (label, value). Rendered as a row of KPI cards."""
    cells = [[Paragraph(f"<para align='center'><font size=18 color='#1F4E79'><b>{v}</b></font></para>", styles["Normal"]) for _, v in items],
             [Paragraph(f"<para align='center'><font size=8 color='#555555'>{l}</font></para>", styles["Normal"]) for l, _ in items]]
    t = Table(cells, colWidths=[(A4[0] - 4 * cm) / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.white),
        ("INNERGRID", (0, 0), (-1, -1), 2, colors.white),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
    ]))
    return t


def counts_table(counts: pd.Series, total: int, label: str, styles, max_rows=25):
    rows = [[label, "Count", "% of respondents"]]
    for name, n in counts.head(max_rows).items():
        rows.append([Paragraph(str(name)[:80], styles["Small"]), int(n), f"{100 * n / total:.1f}%" if total else "-"])
    t = Table(rows, colWidths=[9 * cm, 2.5 * cm, 3.5 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    return t


def add_section(story, styles, title, counts, total, label, chart=None, intro=None):
    story.append(Paragraph(title, styles["H1"]))
    if intro:
        story.append(Paragraph(intro, styles["Normal"]))
        story.append(Spacer(1, 6))
    if counts is None or counts.empty:
        story.append(Paragraph("<i>No data available.</i>", styles["Normal"]))
        return
    if chart is not None:
        story.append(chart)
        story.append(Spacer(1, 6))
    story.append(counts_table(counts, total, label, styles))
    story.append(Spacer(1, 10))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2 * cm, 1.2 * cm, "OpenMS survey statistics")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def build_report(csv_path: str, out_path: str, top: int = 15):
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    # De-duplicate on Submission ID if present
    if COL_ID in df.columns:
        df = df.drop_duplicates(subset=COL_ID)
    total = len(df)

    styles = make_styles()
    story = []

    # ---------------- Title / overview ---------------- #
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph("OpenMS Community Survey", styles["ReportTitle"]))
    story.append(Paragraph(f"Statistics report &middot; generated {datetime.now():%d %B %Y}", styles["Sub"]))

    dates = pd.to_datetime(df.get(COL_SUBMITTED), errors="coerce", utc=True).dt.tz_localize(None) \
        if COL_SUBMITTED in df.columns else pd.Series(dtype="datetime64[ns]")

    unique_resp = df[COL_RESPONDENT].nunique() if COL_RESPONDENT in df.columns else total
    unique_email = df[COL_EMAIL].dropna().str.lower().nunique() if COL_EMAIL in df.columns else None
    n_news = int(is_selected(df[COL_NEWSLETTER]).sum()) if COL_NEWSLETTER in df.columns else 0
    n_reach = int(is_selected(df[COL_REACH_EMAIL]).sum()) if COL_REACH_EMAIL in df.columns else 0

    kpis = [("Submissions", total), ("Unique respondents", unique_resp)]
    if unique_email is not None:
        kpis.append(("Unique emails", unique_email))
    kpis += [("Newsletter sign-ups", n_news), ("Want email contact", n_reach)]
    story.append(kpi_table(kpis, styles))
    story.append(Spacer(1, 12))

    if not dates.dropna().empty:
        story.append(Paragraph(
            f"Responses were collected between <b>{dates.min():%d %b %Y}</b> and "
            f"<b>{dates.max():%d %b %Y}</b>.", styles["Normal"]))
        story.append(Spacer(1, 8))
        tl = timeline_chart(dates)
        if tl:
            story.append(tl)

    # Data quality
    story.append(Paragraph("Data completeness", styles["H1"]))
    completeness_cols = [COL_NAME, COL_EMAIL, COL_AFFIL, COL_ROLE, COL_GITHUB, COL_DISCORD, COL_FEEDBACK]
    comp = {}
    for c in completeness_cols:
        if c in df.columns:
            filled = df[c].fillna("").astype(str).str.strip().ne("").sum()
            comp[c] = int(filled)
    story.append(counts_table(pd.Series(comp), total, "Field filled in", styles))

    story.append(PageBreak())

    # ---------------- Role ---------------- #
    if COL_ROLE in df.columns:
        roles = value_counts_clean(df[COL_ROLE])
        add_section(story, styles, "Respondent roles", roles, total, "Role",
                    chart=pie_chart(roles.head(8), "Role distribution") if len(roles) > 1 else None)

    # ---------------- Affiliation ---------------- #
    if COL_AFFIL in df.columns:
        aff = normalise_affiliation(df[COL_AFFIL])
        story.append(PageBreak())
        add_section(story, styles, f"Top {top} affiliations", aff.head(top), total, "Affiliation",
                    chart=hbar_chart(aff.head(top), "Most common affiliations"),
                    intro=f"{len(aff)} distinct affiliations were reported "
                          f"({int((aff == 1).sum())} appear only once).")

    # ---------------- Interests ---------------- #
    interests = multi_select_counts(df, COL_INTEREST)
    story.append(PageBreak())
    add_section(story, styles, "Areas of interest", interests, total, "Area",
                chart=hbar_chart(interests, "Areas of interest (multi-select)"),
                intro="Respondents could select several areas, so percentages add up to more than 100%.")

    if not interests.empty:
        avg = sum(is_selected(df[c]).astype(int) for c in df.columns if c.startswith(COL_INTEREST + " ("))
        if not isinstance(avg, int):
            story.append(Paragraph(f"Average number of areas selected per respondent: <b>{avg.mean():.2f}</b>.",
                                   styles["Normal"]))

    # Role x interest heatmap
    if COL_ROLE in df.columns and not interests.empty:
        int_cols = {option_label(c, COL_INTEREST): c for c in df.columns if c.startswith(COL_INTEREST + " (")}
        if int_cols:
            top_roles = value_counts_clean(df[COL_ROLE]).head(8).index
            m = pd.DataFrame({lab: [int(is_selected(df.loc[df[COL_ROLE] == r, c]).sum()) for r in top_roles]
                              for lab, c in int_cols.items()}, index=top_roles)
            story.append(Spacer(1, 8))
            hm = heatmap_chart(m, "Interest by role")
            if hm:
                story.append(hm)

    # ---------------- Platforms ---------------- #
    platforms = multi_select_counts(df, COL_PLATFORM)
    story.append(PageBreak())
    add_section(story, styles, "Platforms", platforms, total, "Platform",
                chart=hbar_chart(platforms, "Platforms used / planned (multi-select)"))

    # OS family summary
    if not platforms.empty:
        os_cols = {k: next((c for c in df.columns if c == f"{COL_PLATFORM} ({k})"), None)
                   for k in ["Windows", "Mac", "Linux"]}
        ok = {k: c for k, c in os_cols.items() if c}
        if ok:
            sel = pd.DataFrame({k: is_selected(df[c]) for k, c in ok.items()})
            multi = int((sel.sum(axis=1) > 1).sum())
            story.append(Paragraph(
                f"<b>{multi}</b> respondents ({100 * multi / total:.1f}%) use more than one desktop OS.",
                styles["Normal"]))

    # ---------------- Engagement ---------------- #
    story.append(Paragraph("Community engagement", styles["H1"]))
    eng = {}
    if COL_NEWSLETTER in df.columns:
        eng["Signed up for newsletter"] = n_news
    if COL_REACH_EMAIL in df.columns:
        eng["Happy to be contacted by email"] = n_reach
    for lab, c in [("Provided GitHub handle", COL_GITHUB), ("Provided Discord handle", COL_DISCORD),
                   ("Left additional feedback", COL_FEEDBACK)]:
        if c in df.columns:
            eng[lab] = int(df[c].fillna("").astype(str).str.strip().ne("").sum())
    eng_s = pd.Series(eng).sort_values(ascending=False)
    story.append(hbar_chart(eng_s, "Engagement indicators") or Spacer(1, 1))
    story.append(counts_table(eng_s, total, "Indicator", styles))

    # ---------------- Feedback ---------------- #
    if COL_FEEDBACK in df.columns:
        fb = df[COL_FEEDBACK].dropna().astype(str).str.strip()
        fb = fb[fb != ""]
        story.append(PageBreak())
        story.append(Paragraph("Additional feedback", styles["H1"]))
        story.append(Paragraph(f"{len(fb)} respondents left free-text feedback "
                               f"(names and emails omitted).", styles["Normal"]))
        story.append(Spacer(1, 6))
        for text in fb.head(100):
            safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    .replace("\n", "<br/>"))
            story.append(Paragraph(f"&ldquo;{safe[:1200]}&rdquo;", styles["Quote"]))
        if len(fb) > 100:
            story.append(Paragraph(f"<i>… and {len(fb) - 100} more.</i>", styles["Normal"]))

    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title="OpenMS Community Survey - Statistics", author="Survey report")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Create a PDF statistics report from a survey CSV.")
    ap.add_argument("csv", help="Path to the CSV export")
    ap.add_argument("-o", "--output", default="survey_report.pdf", help="Output PDF path")
    ap.add_argument("--top", type=int, default=15, help="How many top affiliations to show")
    args = ap.parse_args()
    build_report(args.csv, args.output, args.top)
