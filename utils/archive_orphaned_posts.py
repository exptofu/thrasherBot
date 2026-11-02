"""Archive RBA forum threads whose sightings are no longer in sightings.db.

The bot only archives posts it can still see in SQLite (one row per species + hotspot/county
scope). Rows dropped by an earlier prune, by a database reset, or by pointing the bot at the
wrong DB leave threads open forever, because the sighting evidence is gone. This job is the
manual backfill for those threads.

Preview first: run without --apply to list qualifying threads and the reason.
Apply mode: archives them in the forum configured by DISCORD_CHANNEL_ID.

Only threads the bot created are ever archived; member-created posts are skipped, and pinned
posts are skipped too unless --include-pinned is passed. A thread is left open when its newest
stored sighting is inside the retention window, or when its last message is newer than that
window (a guard against archiving a just-created thread whose row has not been written yet).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import discord
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def observation_age_days(record: dict) -> int | None:
    """Days between today and the record's observation date, if it can be parsed."""
    obs_dt = str(record.get("obsDt") or "").strip()
    if not obs_dt:
        return None
    try:
        obs_day = obs_dt.split("T", 1)[0].split(" ", 1)[0]
        return (date.today() - date.fromisoformat(obs_day)).days
    except ValueError:
        return None


def load_db_state(db_path: Path) -> tuple[dict[int, dict], dict[tuple[str, str], int]]:
    """Read thread_id -> post row and (species, scope) -> newest sighting age, without writing."""
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        posts = {
            thread_id: {"species_code": species, "scope": scope}
            for species, scope, thread_id in conn.execute(
                "SELECT species_code, scope, thread_id FROM posts"
            )
        }
        newest: dict[tuple[str, str], int] = {}
        for species, scope, data in conn.execute(
            "SELECT species_code, scope, data FROM sightings"
        ):
            try:
                record = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(record, dict):
                continue
            age_days = observation_age_days(record)
            if age_days is None:
                continue
            key = (species, scope)
            if key not in newest or age_days < newest[key]:
                newest[key] = age_days
    return posts, newest


def thread_last_activity(thread: discord.Thread) -> datetime:
    """Timestamp of the thread's latest message, falling back to the thread's creation."""
    return discord.utils.snowflake_time(thread.last_message_id or thread.id)


def archive_reason(
    thread: discord.Thread,
    post: dict | None,
    newest: dict[tuple[str, str], int],
    cutoff_days: int,
    cutoff_time: datetime,
) -> str | None:
    """Why this thread should be archived, or None to leave it open."""
    if thread_last_activity(thread) >= cutoff_time:
        return None
    if post is not None:
        age_days = newest.get((post["species_code"], post["scope"]))
        if age_days is not None and age_days <= cutoff_days:
            return None
        return (
            f"newest stored sighting {age_days} days old"
            if age_days is not None
            else "post row has no sightings left in the database"
        )
    return "sightings are no longer in the database"


def classify_threads(
    threads: list[discord.Thread],
    bot_id: int | None,
    posts: dict[int, dict],
    newest: dict[tuple[str, str], int],
    cutoff_days: int,
    cutoff_time: datetime,
    *,
    include_pinned: bool,
) -> tuple[list[tuple[discord.Thread, str]], list[discord.Thread], list[discord.Thread]]:
    """Split active threads into (archive targets, skipped pinned, skipped non-bot threads)."""
    bot_threads = [thread for thread in threads if thread.owner_id == bot_id]
    foreign = [thread for thread in threads if thread.owner_id != bot_id]

    targets: list[tuple[discord.Thread, str]] = []
    pinned_skipped: list[discord.Thread] = []
    for thread in sorted(bot_threads, key=thread_last_activity):
        reason = archive_reason(
            thread, posts.get(thread.id), newest, cutoff_days, cutoff_time
        )
        if not reason:
            continue
        if not include_pinned and getattr(thread.flags, "pinned", False):
            pinned_skipped.append(thread)
            continue
        targets.append((thread, reason))
    return targets, pinned_skipped, foreign


async def archive_stale_threads(
    client: discord.Client,
    forum_id: int,
    db_path: Path,
    cutoff_days: int,
    *,
    apply: bool,
    allow_empty_posts: bool,
    include_pinned: bool,
) -> int:
    forum = client.get_channel(forum_id) or await client.fetch_channel(forum_id)
    if not isinstance(forum, discord.ForumChannel):
        raise TypeError(f"Channel {forum_id} is not a forum channel")

    posts, newest = load_db_state(db_path)
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    print(
        f"Forum #{forum.name} ({forum.id}): {len(posts)} post row(s) in {db_path.name}, "
        f"window {cutoff_days} days."
    )

    threads = list(forum.threads)
    if not threads:
        threads = [t for t in await forum.guild.active_threads() if t.parent_id == forum.id]
    active = [thread for thread in threads if not thread.archived]

    bot_id = client.user.id if client.user else None
    targets, pinned_skipped, foreign = classify_threads(
        active, bot_id, posts, newest, cutoff_days, cutoff_time, include_pinned=include_pinned
    )
    print(f"Scanning {len(active) - len(foreign)} active thread(s) created by the bot.")
    if foreign:
        print(f"Skipping {len(foreign)} active thread(s) that the bot did not create:")
        for thread in foreign[:10]:
            print(f"  . #{thread.name} ({thread.id})")
        if len(foreign) > 10:
            print(f"  . ... and {len(foreign) - 10} more")

    if pinned_skipped:
        print(f"Skipping {len(pinned_skipped)} pinned thread(s); pass --include-pinned to archive them:")
        for thread in pinned_skipped[:10]:
            print(f"  . #{thread.name} ({thread.id})")
        if len(pinned_skipped) > 10:
            print(f"  . ... and {len(pinned_skipped) - 10} more")

    if not targets:
        print("Nothing to archive.")
        return 0

    if apply and not posts and not allow_empty_posts:
        print(
            "Refusing to apply: the posts table is empty, which usually means DB_PATH points at "
            "the wrong database or the schema was reset. Re-run with --allow-empty-posts if that "
            "is expected."
        )
        return 0

    guild_me = forum.guild.me
    if apply and (guild_me is None or not forum.permissions_for(guild_me).manage_threads):
        print(f"Missing Manage Threads in #{forum.name}; nothing archived.")
        return 0

    archived = 0
    for thread, reason in targets:
        print(f"  - #{thread.name} ({thread.id}): {reason}")
        if not apply:
            continue
        try:
            await thread.edit(archived=True, reason=f"Stale RBA post: {reason}")
        except discord.HTTPException as error:
            print(f"    [http] could not archive {thread.id}: {error}")
            continue
        archived += 1

    if apply:
        print(f"Archived {archived} of {len(targets)} qualifying thread(s).")
    else:
        print(f"Preview complete: {len(targets)} thread(s) would be archived; none changed.")
    return archived


def parse_args() -> argparse.Namespace:
    back_days = int(os.getenv("EBIRD_BACK_DAYS", "14"))
    parser = argparse.ArgumentParser(
        description="Archive RBA threads whose sightings are no longer in sightings.db."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Archive the qualifying threads instead of previewing them.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / os.getenv("DB_PATH", "sightings.db"),
        help="Path to sightings.db (default: DB_PATH or sightings.db next to bot.py).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=max(1, back_days) * 2,
        help="Inactivity window in days (default: EBIRD_BACK_DAYS * 2).",
    )
    parser.add_argument(
        "--allow-empty-posts",
        action="store_true",
        help="Allow --apply when the posts table is empty (e.g. after a schema reset).",
    )
    parser.add_argument(
        "--include-pinned",
        action="store_true",
        help="Also archive pinned bot posts; pinned posts are skipped by default.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN is missing. Set it in .env or export it.")
        return 1
    channel_id = os.getenv("DISCORD_CHANNEL_ID")
    if not channel_id:
        print("DISCORD_CHANNEL_ID is missing. Set it in .env or export it.")
        return 1
    if not args.db.is_file():
        print(f"Database not found: {args.db}")
        return 1

    intents = discord.Intents.default()

    class ArchiveClient(discord.Client):
        async def on_ready(self):
            try:
                await archive_stale_threads(
                    self,
                    int(channel_id),
                    args.db,
                    args.days,
                    apply=args.apply,
                    allow_empty_posts=args.allow_empty_posts,
                    include_pinned=args.include_pinned,
                )
            except Exception as error:  # pragma: no cover - user-facing maintenance script
                print(f"Archive run failed: {error}")
            finally:
                await self.close()

    client = ArchiveClient(intents=intents)
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
