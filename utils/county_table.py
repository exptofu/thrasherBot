"""Print or post Discord-markdown county listings with channel links and region role mentions."""
import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv

try:
    from region_channels import load_region_config, rba_forum_name
except ImportError:
    from utils.region_channels import load_region_config, rba_forum_name

ROOT = Path(__file__).resolve().parent.parent
MESSAGE_LIMIT = 1900
MAPPING_CHANNEL = "county-mapping"
DESCRIPTION = (
    "**County to channel mapping**\n"
    "Each county lists its region role (ping it to reach that region's birders), "
    "the region chat where sightings are posted, and the RBA forum for its region."
)
MAPPING_ROW = re.compile(
    r"- \*\*.+?\*\*: (?:<@&\d+>|@[^|\n]+) \| "
    r"(?:<#\d+>|#[^|\n]+) \| (?:<#\d+>|#[^|\n]+)"
)


def build_rows() -> list[tuple[str, str, str, str]]:
    regions, region_groups = load_region_config()
    forum_of = {
        region: rba_forum_name(group, group_regions)
        for group, group_regions in region_groups.items()
        for region in group_regions
    }
    rows = []
    for region, counties in regions.items():
        for county in counties:
            channel = f"{region}-chat"
            rows.append((county, region, channel, forum_of[region]))
    return sorted(rows, key=lambda row: row[0].lower())


def render(rows, roles: dict[str, int], channels: dict[str, int]) -> list[str]:
    """Format one line per county, split into messages under Discord's length limit."""
    messages, current = [], ""
    for county, region, channel, forum in rows:
        role = f"<@&{roles[region]}>" if region in roles else f"@{region}"
        chat_link = f"<#{channels[channel]}>" if channel in channels else f"#{channel}"
        forum_link = f"<#{channels[forum]}>" if forum in channels else f"#{forum}"
        line = f"- **{county}**: {role} | {chat_link} | {forum_link}\n"
        if current and len(current) + len(line) > MESSAGE_LIMIT:
            messages.append(current)
            current = ""
        current += line
    if current:
        messages.append(current)
    return messages


async def update_mapping_messages(
    target: discord.TextChannel, bot_user_id: int, texts: list[str]
) -> None:
    existing = []
    async for message in target.history(limit=None, oldest_first=True):
        if message.author.id != bot_user_id:
            continue
        lines = message.content.splitlines()
        if message.content.startswith("**County to channel mapping**\n") or (
            lines and all(MAPPING_ROW.fullmatch(line) for line in lines)
        ):
            existing.append(message)

    mentions = discord.AllowedMentions.none()
    edited = 0
    for message, text in zip(existing, texts):
        if message.content != text:
            await message.edit(content=text, allowed_mentions=mentions)
            edited += 1
    for text in texts[len(existing):]:
        await target.send(text, allowed_mentions=mentions)
    for message in existing[len(texts):]:
        await message.delete()
    print(
        f"Mapping: {edited} edited, {max(0, len(texts) - len(existing))} posted, "
        f"{max(0, len(existing) - len(texts))} obsolete messages deleted."
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--post",
        action="store_true",
        help=f"Update the bot's mapping messages in #{MAPPING_CHANNEL} without pinging (default: print)",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    token = os.getenv("DISCORD_TOKEN")
    try:
        forum_id = int(os.environ["DISCORD_CHANNEL_ID"])
    except (KeyError, ValueError):
        print("DISCORD_CHANNEL_ID must be set in .env")
        return 1
    if not token:
        print("DISCORD_TOKEN is missing; set it in .env")
        return 1

    class TableClient(discord.Client):
        def __init__(self):
            super().__init__(intents=discord.Intents.default())
            self.exit_code = 0
            self.started = False

        async def on_ready(self):
            if self.started:
                return
            self.started = True
            try:
                forum = self.get_channel(forum_id) or await self.fetch_channel(forum_id)
                guild = forum.guild
                roles = {role.name: role.id for role in guild.roles}
                channels = {channel.name: channel.id for channel in guild.channels}
                messages = render(build_rows(), roles, channels)
                if args.post:
                    target = discord.utils.get(guild.text_channels, name=MAPPING_CHANNEL)
                    if target is None:
                        print(f"No text channel named #{MAPPING_CHANNEL}.")
                        self.exit_code = 1
                        return
                    if self.user is None:
                        print("Cannot identify the bot user.")
                        self.exit_code = 1
                        return
                    await update_mapping_messages(
                        target, self.user.id, [DESCRIPTION, *messages]
                    )
                    return
                print(DESCRIPTION)
                for number, message in enumerate(messages, 1):
                    print(f"----- message {number} of {len(messages)} -----")
                    print(message, end="")
            except discord.HTTPException as error:
                print(f"Lookup failed: {error}")
                self.exit_code = 1
            finally:
                await self.close()

    client = TableClient()
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return client.exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
