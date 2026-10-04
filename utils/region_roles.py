"""Create a mentionable role for each region."""
import argparse
import asyncio
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv

try:
    from region_channels import load_region_config
except ImportError:
    from utils.region_channels import load_region_config

ROOT = Path(__file__).resolve().parent.parent


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create mentionable roles for regions."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Create the missing roles (default: preview)"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Seconds between role creations"
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        parser.error("DISCORD_TOKEN is missing; set it in .env")
    try:
        alert_forum_id = int(os.environ["DISCORD_CHANNEL_ID"])
    except (KeyError, ValueError):
        parser.error("DISCORD_CHANNEL_ID must be set in .env")

    try:
        regions, _ = load_region_config()
    except (OSError, SyntaxError, ValueError) as error:
        parser.error(f"Could not load region definitions from bot.py: {error}")

    wanted = list(regions)

    class RoleClient(discord.Client):
        def __init__(self):
            super().__init__(intents=discord.Intents.default())
            self.exit_code = 0
            self.started = False

        async def on_ready(self):
            if self.started:
                return
            self.started = True
            try:
                channel = self.get_channel(alert_forum_id) or await self.fetch_channel(
                    alert_forum_id
                )
                guild = channel.guild
                if args.apply and not guild.me.guild_permissions.manage_roles:
                    print("The bot lacks the Manage Roles permission.")
                    self.exit_code = 1
                    return

                existing = {role.name for role in guild.roles}
                missing = [name for name in wanted if name not in existing]
                print(f"{len(wanted) - len(missing)} roles exist; {len(missing)} to create.")
                for index, name in enumerate(missing):
                    if not args.apply:
                        print(f"Would create role '{name}'")
                        continue
                    if index:
                        await asyncio.sleep(args.delay)
                    await guild.create_role(
                        name=name, mentionable=True, reason="Regional ping role"
                    )
                    print(f"Created role '{name}'")
                if missing and not args.apply:
                    print("Preview only; pass --apply to create these roles.")
            except discord.HTTPException as error:
                print(f"Role setup failed: {error}")
                self.exit_code = 1
            finally:
                await self.close()

    client = RoleClient()
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return client.exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
