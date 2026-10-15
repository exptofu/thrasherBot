"""Assign the unregistered role to members who have not completed registration."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

UNREGISTERED_MESSAGE = (
    "@unregistered - if you are getting this ping, you have not completed registration.\n"
    "Please read the messages in #rules-and-info and follow the prompts!"
)


async def assign_unregistered_members(
    guild: discord.Guild,
    member_role_name: str,
    unregistered_role_name: str,
    *,
    apply: bool,
) -> list[discord.Member]:
    member_role = discord.utils.get(guild.roles, name=member_role_name)
    if member_role is None:
        raise ValueError(f"The role '{member_role_name}' was not found in guild '{guild.name}'.")

    unregistered_role = discord.utils.get(guild.roles, name=unregistered_role_name)
    if unregistered_role is None:
        raise ValueError(
            f"The role '{unregistered_role_name}' was not found in guild '{guild.name}'."
        )

    eligible = [
        member
        for member in guild.members
        if not member.bot and member_role not in member.roles
    ]

    print(
        f"Found {len(eligible)} members without the '{member_role_name}' role in '{guild.name}'."
    )

    for member in eligible:
        print(f"  - {member} ({member.id})")
        if not apply:
            continue
        try:
            await member.add_roles(unregistered_role, reason="User has not completed registration")
            print(f"    [applied] added '{unregistered_role_name}' to {member}")
        except discord.Forbidden:
            print(f"    [forbidden] could not add '{unregistered_role_name}' to {member}")
        except discord.HTTPException as exc:
            print(f"    [http] could not add '{unregistered_role_name}' to {member}: {exc}")

    return eligible


async def send_unregistered_notice(
    guild: discord.Guild,
    channel_name: str,
    *,
    apply: bool,
) -> discord.abc.Messageable | None:
    channel = discord.utils.get(guild.text_channels, name=channel_name)
    if channel is None:
        print(f"No #{channel_name} text channel was found in '{guild.name}'.")
        return None

    print(f"Posting reminder to #{channel_name} in '{guild.name}'.")
    if not apply:
        print(f"Preview only; message would be: {UNREGISTERED_MESSAGE}")
        return channel

    message = await channel.send(UNREGISTERED_MESSAGE)
    print(f"Sent reminder message {message.id} to #{channel_name}.")
    return channel


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assign the unregistered role to all members who do not yet have the member role."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the role changes and send the reminder message (default is preview only).",
    )
    parser.add_argument(
        "--member-role",
        default="member",
        help="Role name to treat as the completed-registration role.",
    )
    parser.add_argument(
        "--unregistered-role",
        default="unregistered",
        help="Role name to assign to users who have not completed registration.",
    )
    parser.add_argument(
        "--channel",
        default="discord-help",
        help="Text channel to send the reminder to.",
    )
    args = parser.parse_args()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        parser.error("DISCORD_TOKEN is missing. Set it in .env or export it.")

    class UnregisteredClient(discord.Client):
        async def on_ready(self):
            guild = self.guilds[0] if self.guilds else None
            if guild is None:
                print("No guilds are available for this bot token.")
                await self.close()
                return

            if not guild.me.guild_permissions.manage_roles:
                print("The bot lacks the Manage Roles permission.")
                await self.close()
                return

            try:
                await assign_unregistered_members(
                    guild,
                    args.member_role,
                    args.unregistered_role,
                    apply=args.apply,
                )
                await send_unregistered_notice(guild, args.channel, apply=args.apply)
            except ValueError as exc:
                print(exc)
            finally:
                await self.close()

    client = UnregisteredClient(intents=discord.Intents.default())
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
