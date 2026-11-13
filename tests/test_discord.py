from datetime import datetime, timedelta, timezone

import ingest.discord_snapshot as d
from ingest.common import read_table

DAY = datetime(2026, 11, 10, tzinfo=timezone.utc)
BASE = 16 * 10**17  # recent snowflake


def member(i):
    return {"user": {"id": str(1000 + i), "username": f"User{i}", "global_name": None, "bot": False},
            "nick": None, "joined_at": (datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)).isoformat()}


class FakeDiscord(d.Discord):
    def __init__(self, members=(), messages=(), members_allowed=True):
        self.members, self.messages, self.members_allowed = list(members), list(messages), members_allowed
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == "/guilds/g":
            return {"approximate_member_count": len(self.members), "approximate_presence_count": 1}
        if path.endswith("/channels"):
            return [{"id": "c1", "type": 0, "name": "general"}, {"id": "c2", "type": 2, "name": "voice"}]
        if path.endswith("/members"):
            if not self.members_allowed:
                return None
            a = int(params["after"])
            return sorted((m for m in self.members if int(m["user"]["id"]) > a),
                          key=lambda m: int(m["user"]["id"]))[:params["limit"]]
        a = int(params["after"])  # messages, newest first like Discord
        out = [i for i in self.messages if i > a][:100]
        return [{"id": str(i), "timestamp": "2026-11-09T10:00:00+00:00", "author": {"username": "Dev"}}
                for i in reversed(out)]


def test_members_paging_leave_and_rejoin(data_dir):
    dc = FakeDiscord(members=[member(i) for i in range(1500)])
    d.sync_members(dc, "g", DAY)
    assert len(read_table("discord_members")) == 1500  # two pages of 1000

    dc.members = [m for m in dc.members if m["user"]["id"] != "1007"]
    d.sync_members(dc, "g", DAY + timedelta(days=1))
    m = read_table("discord_members")
    assert m.left_seen.notna().sum() == 1 and len(m) == 1500

    dc.members.append(member(7))
    d.sync_members(dc, "g", DAY + timedelta(days=2))
    m = read_table("discord_members")
    assert m.left_seen.notna().sum() == 0 and m.user_id.is_unique
    assert m.loc[m.user_id == "1007", "first_seen"].iloc[0] == DAY.replace(tzinfo=None)


def test_members_without_intent_keeps_table(data_dir):
    d.sync_members(FakeDiscord(members=[member(1)]), "g", DAY)
    d.sync_members(FakeDiscord(members_allowed=False), "g", DAY)
    assert len(read_table("discord_members")) == 1


def test_messages_incremental(data_dir, monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "x")
    monkeypatch.setenv("DISCORD_GUILD_ID", "g")
    fake = FakeDiscord(messages=range(BASE, BASE + 103))
    monkeypatch.setattr(d, "Discord", lambda token: fake)
    d.main()
    assert len(read_table("discord_messages")) == 103

    fake.messages = list(fake.messages) + [BASE + 500, BASE + 501]
    fake.calls.clear()
    d.main()
    msgs = read_table("discord_messages")
    assert len(msgs) == 105 and msgs.message_id.is_unique
    after = [int(p["after"]) for path, p in fake.calls if path.endswith("/messages")]
    assert after == [BASE + 102]                 # resumes from last seen id, voice channel skipped
    assert len(read_table("discord_daily")) == 1  # same day -> one row
