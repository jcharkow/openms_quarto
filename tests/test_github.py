import pandas as pd

import ingest.github as g
from ingest.common import read_table


class Resp:
    def __init__(self, data):
        self._data, self.links = data, {}

    def json(self):
        return self._data


class FakeGitHub(g.GitHub):
    def __init__(self, issues):
        self.issues = issues
        self.since = []
        self.commits = [commit("a", "2026-01-05T00:00:00Z"), commit("b", "2026-01-06T00:00:00Z", merge=True)]

    def discussions(self, repo):
        return [{"number": 7, "createdAt": "2026-01-04T00:00:00Z", "author": {"login": "U", "__typename": "User"},
                 "category": {"name": "Q&A"}, "answer": None}]

    def get(self, url, params=None, accept=None, optional=False):
        if "/traffic/" in url:
            return None if optional else Resp([])
        if url.endswith("/issues"):
            self.since.append((params or {}).get("since"))
            return Resp(self.issues)
        if url.endswith("/commits"):
            return Resp(self.commits)
        if url.endswith("/repos/o/r"):
            return Resp({"stargazers_count": 5, "forks_count": 1, "subscribers_count": 2, "open_issues_count": 3})
        return Resp([])


def commit(sha, date, merge=False, login="Dev"):
    return {"sha": sha, "author": {"login": login, "type": "User"},
            "commit": {"author": {"date": date}, "committer": {"date": date}},
            "parents": [{}, {}] if merge else [{}]}


def issue(n, updated):
    return {"number": n, "user": {"login": "Dev", "type": "User"}, "state": "open", "title": "t",
            "created_at": "2026-01-01T00:00:00Z", "updated_at": updated, "closed_at": None,
            "author_association": "MEMBER", "comments": 0,
            **({"pull_request": {"merged_at": None}} if n % 2 else {})}


def test_issues_incremental(data_dir, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOS", "o/r")
    fake = FakeGitHub([issue(1, "2026-01-02T00:00:00Z"), issue(2, "2026-01-03T00:00:00Z")])
    monkeypatch.setattr(g, "GitHub", lambda token: fake)
    g.main()
    assert len(read_table("github_issues")) == 2

    fake.issues = [issue(2, "2026-02-01T00:00:00Z"), issue(3, "2026-02-01T00:00:00Z")]
    g.main()
    iss = read_table("github_issues")
    assert sorted(iss.number) == [1, 2, 3]              # merged, not replaced
    assert iss.set_index("number").loc[2, "updated_at"] == pd.Timestamp("2026-02-01")
    assert fake.since[0] is None and fake.since[1].startswith("2026-01-02")


def test_commits_discussions_and_services(data_dir, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOS", "o/r=core|python")
    fake = FakeGitHub([])
    monkeypatch.setattr(g, "GitHub", lambda token: fake)
    g.main()
    fake.commits = [commit("b", "2026-01-06T00:00:00Z", merge=True), commit("c", "2026-02-01T00:00:00Z")]
    g.main()
    c = read_table("github_commits")
    assert sorted(c.sha) == ["a", "b", "c"] and c.is_merge.sum() == 1 and set(c.author) == {"dev"}
    assert read_table("github_discussions").category.tolist() == ["Q&A"]
    svc = read_table("github_repo_services")
    assert sorted(svc.service) == ["core", "python"]


def test_empty_repo_list_and_repo_without_releases(data_dir, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOS", "")
    monkeypatch.setattr(g, "GitHub", lambda token: FakeGitHub([]))
    g.main()
    assert read_table("github_daily") is None            # nothing written, dashboard shows placeholders

    monkeypatch.setenv("GITHUB_REPOS", "o/r")
    g.main()
    rel = read_table("github_releases")
    assert rel.empty and "repo" in rel.columns and "published_at" in rel.columns
