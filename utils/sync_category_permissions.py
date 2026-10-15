"""Preview or sync guild channel permissions with their parent categories."""
import argparse
import asyncio
import os
import sys

import discord
from dotenv import load_dotenv


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or sync channel permissions from their parent categories."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply the permission syncs"
    )
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        parser.error("DISCORD_TOKEN is missing; set it in .env")
    try:
        channel_id = int(os.environ["DISCORD_CHANNEL_ID"])
    except (KeyError, ValueError):
        parser.error("DISCORD_CHANNEL_ID must be set to the alert forum ID in .env")

    class PermissionSyncClient(discord.Client):
        def __init__(self):
            super().__init__(intents=discord.Intents.default())
            self.exit_code = 0
            self.sync_started = False

        async def on_ready(self):
            if self.sync_started:
                return
            self.sync_started = True
            try:
                alert_channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
                guild = alert_channel.guild
                channels = sorted(guild.channels, key=lambda item: (item.position, item.id))
                changed = 0
                failed = 0
                for channel in channels:
                    if isinstance(channel, discord.CategoryChannel):
                        continue
                    if channel.id == channel_id:
                        print(f"Skipped alert forum: {channel.name} ({channel.id})")
                        continue
                    if channel.category is None:
                        print(f"Skipped channel without a category: {channel.name} ({channel.id})")
                        continue
                    if channel.permissions_synced:
                        print(f"Already synced: {channel.name} ({channel.id})")
                        continue
                    if not args.apply:
                        print(f"Would sync: {channel.name} ({channel.id}) from {channel.category.name}")
                        changed += 1
                        continue
                    try:
                        await channel.edit(
                            sync_permissions=True,
                            reason="Sync channel permissions with parent category",
                        )
                        print(f"Synced: {channel.name} ({channel.id})")
                        changed += 1
                    except discord.HTTPException as error:
                        print(f"Failed to sync {channel.name} ({channel.id}): {error}")
                        failed += 1

                action = "Synced" if args.apply else "Would sync"
                print(f"{action} {changed} channel(s); {failed} failure(s).")
                if failed:
                    self.exit_code = 1
                if not args.apply:
                    print("Preview only. Add --apply to sync these channel permissions.")
            except discord.NotFound:
                print(f"Alert forum {channel_id} was not found.")
                self.exit_code = 1
            except discord.HTTPException as error:
                print(f"Discord request failed: {error}")
                self.exit_code = 1
            finally:
                await self.close()

    client = PermissionSyncClient()
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return client.exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))