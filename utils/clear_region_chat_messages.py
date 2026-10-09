"""Delete only the bot's own messages from regional chat channels and the alert forum.

Preview first: run without --apply to list channels and message counts.
Apply mode: deletes the bot's messages in text channels whose names end with "-chat"
and in the Discord forum referenced by DISCORD_CHANNEL_ID.
"""

import argparse
import asyncio
import os
from pathlib import Path

import discord
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


async def delete_bot_thread_if_owned(thread: discord.Thread, bot_id: int, apply: bool) -> int:
    if getattr(thread, "owner_id", None) != bot_id:
        return 0

    print(f"  - bot-owned thread: #{thread.name} ({thread.id})")
    if apply:
        try:
            await thread.delete()
            return 1
        except discord.Forbidden:
            print(f"    [forbidden] could not delete thread {thread.id}")
        except discord.HTTPException as exc:
            print(f"    [http] could not delete thread {thread.id}: {exc}")
    return 0


async def delete_bot_messages_in_channel(channel: discord.abc.Messageable, bot_id: int, apply: bool) -> int:
    deleted = 0
    print(f"Checking #{getattr(channel, 'name', channel.id)}...")
    try:
        async for message in channel.history(limit=None):
            if message.author.id != bot_id:
                continue
            print(f"  - bot message: {message.id} | {message.created_at.isoformat()} | {message.content[:80]}")
            if apply:
                try:
                    await message.delete()
                    deleted += 1
                except discord.Forbidden:
                    print(f"    [forbidden] could not delete message {message.id}")
                except discord.HTTPException as exc:
                    print(f"    [http] could not delete message {message.id}: {exc}")
    except AttributeError:
        if isinstance(channel, discord.ForumChannel):
            for thread in channel.threads:
                deleted += await delete_bot_thread_if_owned(thread, bot_id, apply)
        else:
            raise
    except discord.Forbidden:
        print(f"  [forbidden] skipped #{getattr(channel, 'name', channel.id)}")
    except discord.HTTPException as exc:
        print(f"  [http] skipped #{getattr(channel, 'name', channel.id)}: {exc}")
    return deleted


async def list_region_chat_messages(client: discord.Client, guild: discord.Guild, apply: bool) -> int:
    bot_id = client.user.id
    deleted = 0
    total = 0

    for channel in guild.text_channels:
        if not channel.name.endswith("-chat"):
            continue

        total += 1
        deleted += await delete_bot_messages_in_channel(channel, bot_id, apply)

    alert_forum_id = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))
    if alert_forum_id:
        forum = guild.get_channel(alert_forum_id) or await client.fetch_channel(alert_forum_id)
        if isinstance(forum, discord.ForumChannel):
            total += 1
            deleted += await delete_bot_messages_in_channel(forum, bot_id, apply)

    if apply:
        print(f"Deleted {deleted} bot messages across {total} checked channels/forums.")
    else:
        print(f"Preview complete: {total} channels/forums checked; no messages were deleted.")
    return deleted


async def main() -> int:
    parser = argparse.ArgumentParser(description="Delete the bot's messages in -chat channels and the configured forum.")
    parser.add_argument("--apply", action="store_true", help="Actually delete the bot messages instead of previewing them.")
    args = parser.parse_args()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        parser.error("DISCORD_TOKEN is missing. Set it in .env or export it.")

    intents = discord.Intents.default()
    intents.message_content = True

    class CleanupClient(discord.Client):
        async def on_ready(self):
            try:
                guild = self.guilds[0]
            except IndexError:
                print("No guilds are available for this bot token.")
                await self.close()
                return

            try:
                await list_region_chat_messages(self, guild, args.apply)
            except Exception as exc:  # pragma: no cover - user-facing cleanup script
                print(f"Cleanup failed: {exc}")
            finally:
                await self.close()

    client = CleanupClient(intents=intents)
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
