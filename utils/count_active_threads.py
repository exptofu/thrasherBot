"""Count active Discord threads across a guild and by parent channel.

Archived threads are intentionally excluded: Discord's active-thread limit applies to active
threads, not the historical posts in a forum's Older Posts list.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections import Counter
from pathlib import Path

import discord
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count active threads across a guild and group them by parent channel."
    )
    parser.add_argument(
        "--guild-id",
        type=int,
        help="Guild to check. Defaults to the guild containing DISCORD_CHANNEL_ID.",
    )
    return parser.parse_args()


async def count_active_threads(client: discord.Client, args: argparse.Namespace) -> None:
    guild_id = args.guild_id
    forum_id_value = os.getenv("DISCORD_CHANNEL_ID")
    if guild_id is None and forum_id_value:
        channel = client.get_channel(int(forum_id_value))
        if channel is None:
            channel = await client.fetch_channel(int(forum_id_value))
        if not isinstance(channel, discord.ForumChannel):
            raise TypeError(f"DISCORD_CHANNEL_ID {forum_id_value} is not a forum channel")
        guild = channel.guild
        alert_forum_id = channel.id
    elif guild_id is not None:
        guild = client.get_guild(guild_id)
        if guild is None:
            raise ValueError(f"Guild {guild_id} is not available to this bot")
        alert_forum_id = int(forum_id_value) if forum_id_value else None
    elif len(client.guilds) == 1:
        guild = client.guilds[0]
        alert_forum_id = None
    else:
        raise ValueError(
            "Set DISCORD_CHANNEL_ID in .env or pass --guild-id (the bot is in "
            f"{len(client.guilds)} guilds)."
        )

    threads = await guild.active_threads()
    counts = Counter(thread.parent_id for thread in threads)
    channel_names = {channel.id: channel.name for channel in guild.channels}

    print(f"Guild: {guild.name} ({guild.id})")
    print(f"Guild-wide active threads: {len(threads)}")
    if alert_forum_id is not None:
        print(
            f"Configured alert forum active threads: {counts[alert_forum_id]} "
            f"(#{channel_names.get(alert_forum_id, 'unknown')}, {alert_forum_id})"
        )
    print("Active threads by parent channel:")
    for parent_id, count in counts.most_common():
        print(f"  #{channel_names.get(parent_id, 'unknown')} ({parent_id}): {count}")
    print("Archived threads are not included.")


async def main() -> int:
    args = parse_args()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN is missing. Set it in .env or export it.")
        return 1

    class CountClient(discord.Client):
        async def on_ready(self):
            try:
                await count_active_threads(self, args)
            except Exception as error:  # pragma: no cover - user-facing utility
                print(f"Count failed: {error}")
            finally:
                await self.close()

    client = CountClient(intents=discord.Intents.default())
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
