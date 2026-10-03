import argparse
import asyncio
import os
import sys

import discord
from dotenv import load_dotenv


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or delete every post in a Discord forum."
    )
    parser.add_argument(
        "--delete", action="store_true", help="Delete posts after confirmation"
    )
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        parser.error("DISCORD_TOKEN is missing; set it in .env")
    try:
        channel_id = int(os.environ["DISCORD_CHANNEL_ID"])
    except (KeyError, ValueError):
        parser.error("DISCORD_CHANNEL_ID must be set to the forum channel ID in .env")

    class DiscussionCleaner(discord.Client):
        def __init__(self):
            super().__init__(intents=discord.Intents.default())
            self.exit_code = 0
            self.cleanup_started = False

        async def on_ready(self):
            if self.cleanup_started:
                return
            self.cleanup_started = True
            try:
                forum = await self.fetch_channel(channel_id)
                if not isinstance(forum, discord.ForumChannel):
                    print(f"Channel {channel_id} is not a forum channel.")
                    self.exit_code = 1
                    return

                threads = {thread.id: thread for thread in forum.threads}
                for thread in await forum.guild.active_threads():
                    if thread.parent_id == forum.id:
                        threads[thread.id] = thread
                async for thread in forum.archived_threads(limit=None):
                    threads[thread.id] = thread

                posts = sorted(threads.values(), key=lambda item: item.id)
                for thread in posts:
                    print(f"{thread.name} ({thread.id})")
                print(f"Found {len(posts)} post(s) in {forum.name}.")
                if not args.delete:
                    print("Preview only. Add --delete to remove these posts.")
                    return

                confirmation = input(f"Type DELETE {forum.id} to continue: ")
                if confirmation != f"DELETE {forum.id}":
                    print("Confirmation did not match; nothing was deleted.")
                    return

                deleted = 0
                for thread in posts:
                    try:
                        await thread.delete(reason="Testing cleanup")
                        deleted += 1
                    except discord.HTTPException as error:
                        print(f"Stopped after deleting {deleted} post(s): {error}")
                        print("The bot needs the Manage Threads permission in the forum.")
                        self.exit_code = 1
                        return
                print(f"Deleted {deleted} post(s).")
            except discord.NotFound:
                print(f"Forum channel {channel_id} was not found.")
                self.exit_code = 1
            except discord.HTTPException as error:
                print(f"Discord request failed: {error}")
                self.exit_code = 1
            finally:
                await self.close()

    client = DiscussionCleaner()
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return client.exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))