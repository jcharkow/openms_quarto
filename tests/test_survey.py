import pandas as pd

from ingest.common import clean_discord_handle, clean_github_handle, tidy_survey
from ingest.tally import to_export_frame

ROLE = "Please Select the Option that Best Describes Your Role"
INTEREST = "Please Select Your Areas of Interest"
NEWS = "Untitled checkboxes field (Sign Me Up for the OpenMS Newsletter)"


def test_handles():
    assert clean_github_handle("https://github.com/Foo-Bar/") == "foo-bar"
    assert clean_github_handle("@Foo") == "foo"
    assert clean_github_handle(None) is None
    assert clean_discord_handle("@Dev#1234") == "dev"
    assert clean_discord_handle("  ") is None


def test_tidy_survey_drops_pii_and_groups_affiliations():
    df = pd.DataFrame({
        "Submission ID": ["a", "b", "b", "c"],
        "Name": ["Ann", "Bob", "Bob", None],
        "Email": ["Ann@Example.org", "bob@example.org", "bob@example.org", "ann@example.org "],
        "Affiliation": ["ETH Zurich", "eth zurich", "eth zurich", "MIT"],
        ROLE: ["Postdoc", "PhD Student", "PhD Student", None],
        f"{INTEREST} (DIA)": [True, False, False, True],
        f"{INTEREST} (Metabolomics)": [True, True, True, False],
        NEWS: ["Sign Me Up for the OpenMS Newsletter", None, None, ""],
    })
    resp, choices = tidy_survey(df)
    assert len(resp) == 3                                   # duplicate submission removed
    assert "Name" not in resp and "Email" not in resp
    assert not resp.astype(str).apply(lambda c: c.str.contains("@example.org", case=False)).any().any()
    assert resp.email_hash.nunique() == 2                   # Ann counted once (case/whitespace)
    assert resp.affiliation_norm.nunique() == 2             # ETH variants grouped
    assert resp.newsletter.tolist() == [True, False, False]
    assert sorted(choices[choices.submission_id == "a"].option) == ["DIA", "Metabolomics"]


def test_comma_separated_multiselect_fallback():
    df = pd.DataFrame({"Submission ID": ["a"], INTEREST: ["DIA, Metabolomics"]})
    _, choices = tidy_survey(df)
    assert sorted(choices.option) == ["DIA", "Metabolomics"]


def test_tally_api_matches_csv_layout():
    questions = [
        {"id": "q1", "title": ROLE, "fields": [{"uuid": "o1", "title": "Postdoc"}]},
        {"id": "q2", "title": INTEREST, "fields": [{"uuid": "i1", "title": "DIA"}]},
        {"id": "q3", "title": "", "fields": [{"uuid": "n1", "title": "Sign Me Up for the OpenMS Newsletter"}]},
        {"id": "q4", "title": "GitHub Handle"},
    ]
    subs = [{"id": "S1", "submittedAt": "2026-11-01T10:00:00Z", "responses": [
        {"questionId": "q1", "respondentId": "R1", "answer": ["o1"]},
        {"questionId": "q2", "respondentId": "R1", "answer": ["i1", {"text": "Metabolomics"}]},
        {"questionId": "q3", "respondentId": "R1", "answer": ["n1"]},
        {"questionId": "q4", "respondentId": "R1", "answer": "github.com/Ann"},
    ]}]
    df = to_export_frame(questions, subs)
    assert df.loc[0, ROLE] == "Postdoc"
    assert bool(df.loc[0, NEWS])
    resp, choices = tidy_survey(df)
    assert resp.loc[0, "github_handle"] == "ann"
    assert resp.loc[0, "respondent_id"] == "R1"
    assert sorted(choices.option) == ["DIA", "Metabolomics"]
