#!/usr/bin/env python3
"""
Snapshot Discord server metrics into parquet. Run daily: Discord has no history API,
so member-count history only exists from the first day this runs.

    python -m ingest.discord_snapshot    # DISCORD_BOT_TOKEN, DISCORD_GUILD_ID

Tables (data/*.parquet):
  discord_daily     one row per day: approximate member + online counts
  discord_members   one row per user ever seen: usernames, joined_at (from Discord),
                    first_seen / last_seen / left_seen (from our runs). Needs the bot's
                    "Server Members Intent" (developer portal -> Bot -> Privileged Gateway Intents).
  discord_messages  one row per message: channel, author username, timestamp
                    (no message content is stored). Fetched incrementally per channel;
                    the first run goes back DISCORD_BACKFILL_DAYS (default 180).

Bot setup: create an application at https://discord.com/developers/applications, add a bot,
invite it with the "View Channels" and "Read Message History" permissions, and switch on the
"Server Members Intent". The Message Content intent is NOT needed. Threads and forum posts are not counted.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from ingest.common import read_table, require_env, write_table

API = "https://discord.com/api/v10"
DISCORD_EPOCH_MS = 1420070400000
TEXT_CHANNEL_TYPES = {0, 5}  # text, announcement


def snowflake_for(dt: datetime) -> int:
    return (int(dt.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22


class Discord:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bot {token}",
                               "User-Agent": "DiscordBot (community-metrics, 1.0)"})

    def get(self, path, params=None):
        while True:
            r = self.s.get(API + path, params=params, timeout=60)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 1)) + 0.1)
                continue
            if r.status_code == 403:
                return None  # bot can't see this channel
            r.raise_for_status()
            return r.json()


def fetch_members(dc: Discord, guild_id: str) -> list[dict] | None:
    """Current member list (needs the Server Members Intent). None if not allowed."""
    out, after = [], "0"
    while True:
        batch = dc.get(f"/guilds/{guild_id}/members", {"limit": 1000, "after": after})
        if batch is None:
            return None
        out += batch
        if len(batch) < 1000:
            return out
        after = str(max(int(m["user"]["id"]) for m in batch))


def sync_members(dc: Discord, guild_id: str, now: datetime):
    """
    discord_members: one row per user ever seen. joined_at comes from Discord; first_seen/last_seen/
    left_seen are from our own runs, so departures are only known from the first run onwards.
    """
    members = fetch_members(dc, guild_id)
    if members is None:
        print("  member list not allowed: enable 'Server Members Intent' for the bot in the developer portal")
        return
    today = pd.Timestamp(now.date())

    def low(v):
        return v.lower() if v else None

    cur = pd.DataFrame([{
        "user_id": m["user"]["id"],
        "username": low(m["user"].get("username")),
        "global_name": low(m["user"].get("global_name")),
        "nick": low(m.get("nick")),
        "is_bot": bool(m["user"].get("bot")),
        "joined_at": pd.to_datetime(m.get("joined_at"), utc=True).tz_localize(None),
    } for m in members])
    cur["last_seen"] = today
    cur["left_seen"] = pd.NaT

    old = read_table("discord_members")
    if old is None or old.empty:
        cur["first_seen"] = today
        out = cur
    else:
        first = old.set_index("user_id").first_seen
        cur["first_seen"] = cur.user_id.map(first).fillna(today)
        gone = old[~old.user_id.isin(cur.user_id)].copy()
        gone["left_seen"] = gone.left_seen.fillna(today)
        out = pd.concat([cur, gone], ignore_index=True)
    out["first_seen"] = pd.to_datetime(out.first_seen)
    write_table(out, "discord_members")


def main():
    dc = Discord(require_env("DISCORD_BOT_TOKEN"))
    guild_id = require_env("DISCORD_GUILD_ID")
    backfill = int(os.environ.get("DISCORD_BACKFILL_DAYS", 180))
    now = datetime.now(timezone.utc)
    print("Discord")

    g = dc.get(f"/guilds/{guild_id}", {"with_counts": "true"})
    daily = pd.DataFrame([{"date": pd.Timestamp(now.date()), "members": g["approximate_member_count"],
                           "online": g["approximate_presence_count"]}])
    old = read_table("discord_daily")
    if old is not None:
        daily = pd.concat([old, daily]).drop_duplicates("date", keep="last")
    write_table(daily.sort_values("date").reset_index(drop=True), "discord_daily")

    sync_members(dc, guild_id, now)

    old_msgs = read_table("discord_messages")
    last_seen = {}
    if old_msgs is not None and not old_msgs.empty:
        last_seen = old_msgs.groupby("channel_id").message_id.max().to_dict()

    new = []
    for ch in dc.get(f"/guilds/{guild_id}/channels") or []:
        if ch.get("type") not in TEXT_CHANNEL_TYPES:
            continue
        after = last_seen.get(ch["id"], snowflake_for(now - timedelta(days=backfill)))
        n = 0
        while True:
            batch = dc.get(f"/channels/{ch['id']}/messages", {"after": str(after), "limit": 100})
            if not batch:
                break
            for m in batch:
                a = m.get("author") or {}
                new.append({"channel_id": ch["id"], "channel": ch.get("name"), "message_id": int(m["id"]),
                            "author": (a.get("username") or "").lower() or None,
                            "author_is_bot": bool(a.get("bot")),
                            "created_at": pd.to_datetime(m["timestamp"], utc=True).tz_localize(None)})
            after = max(int(m["id"]) for m in batch)
            n += len(batch)
            if len(batch) < 100:
                break
        if n:
            print(f"  #{ch.get('name')}: {n} new messages")

    msgs = pd.DataFrame(new, columns=["channel_id", "channel", "message_id", "author", "author_is_bot", "created_at"])
    if old_msgs is not None:
        msgs = pd.concat([old_msgs, msgs]).drop_duplicates("message_id", keep="last")
    msgs["channel_id"] = msgs["channel_id"].astype(str)
    msgs["message_id"] = msgs["message_id"].astype("int64")
    write_table(msgs.reset_index(drop=True), "discord_messages")


if __name__ == "__main__":
    main()
