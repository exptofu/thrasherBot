"""Create, sync, and order regional Discord channels."""
import argparse
import ast
import asyncio
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent


def _literal_assignments(names: set[str]) -> dict:
    tree = ast.parse((ROOT / "bot.py").read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in names):
            found[node.targets[0].id] = ast.literal_eval(node.value)
    if set(found) != names:
        raise ValueError(f"bot.py must define literal {', '.join(sorted(names))}")
    return found


def load_region_config() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Read literal region definitions from bot.py without importing the bot."""
    config = _literal_assignments({"REGIONS", "REGION_GROUPS"})
    return config["REGIONS"], config["REGION_GROUPS"]


def county_slug(county: str) -> str:
    return county.lower().removesuffix(" county").replace(" ", "-")


def load_county_overrides(
    regions: dict[str, list[str]],
) -> tuple[dict[str, list[str]], set[str]]:
    """Return override channel names per region and regions with every county overridden."""
    overrides = _literal_assignments({"COUNTY_OVERRIDES"})["COUNTY_OVERRIDES"]
    by_county = {
        county_slug(county): region
        for region, counties in regions.items()
        for county in counties
    }
    result: dict[str, list[str]] = {}
    for county in overrides:
        slug = county_slug(county)
        if slug not in by_county:
            raise ValueError(f"COUNTY_OVERRIDES county '{county}' is not in any region")
        names = result.setdefault(by_county[slug], [])
        if f"{slug}-rarities" not in names:
            names.append(f"{slug}-rarities")
    fully_overridden = {
        region for region, counties in regions.items()
        if counties and {county_slug(c) for c in counties} <= {county_slug(c) for c in overrides}
    }
    return result, fully_overridden


async def _on(target: str, coro):
    """Await coro, recording which Discord target failed on any HTTP error."""
    try:
        return await coro
    except discord.HTTPException as error:
        if not hasattr(error, "target"):
            error.target = target
        raise


async def ensure_region_tags(channel: discord.ForumChannel, regions: dict[str, list[str]]):
    have = {tag.name for tag in channel.available_tags}
    missing = [region for region in regions if region not in have]
    if missing:
        await _on(
            f"alert forum #{channel.name} ({channel.id}): adding tags",
            channel.edit(
                available_tags=[
                    *channel.available_tags,
                    *(discord.ForumTag(name=region) for region in missing),
                ]
            ),
        )


def channel_specs(
    region: str, county_channels: dict[str, list[str]], fully_overridden: set[str]
) -> list[tuple[str, str]]:
    """Channel (name, topic) pairs for a region and its county overrides, in display order."""
    specs = []
    if region not in fully_overridden:
        specs += [
            (f"{region}-rarities", f"Rarity sightings and discussion for {region}"),
            (f"{region}-banter", f"General discussion for {region}"),
        ]
    for rarities in county_channels.get(region, []):
        county = rarities.removesuffix("-rarities")
        specs += [
            (rarities, f"Rarity sightings for {county}"),
            (f"{county}-banter", f"General discussion for {county}"),
        ]
    return specs


async def ensure_region_channels(
    channel: discord.ForumChannel,
    region_groups: dict[str, list[str]],
    county_channels: dict[str, list[str]],
    fully_overridden: set[str],
    move_delay_seconds: float,
):
    """Create and group regional rarities, county override, and banter text channels."""
    guild = channel.guild
    text_channels = {text.name: text for text in guild.text_channels}
    categories = {category.name: category for category in guild.categories}
    moves_applied = 0
    for group, regions in region_groups.items():
        category = categories.get(group)
        if category is None:
            category = await _on(f"creating category '{group}'", guild.create_category(group))
            categories[group] = category
        ordered_regions = sorted(regions)
        for region in ordered_regions:
            for text_name, topic in channel_specs(region, county_channels, fully_overridden):
                text = text_channels.get(text_name)
                if text is None:
                    text = await _on(
                        f"creating text channel '{text_name}' in category '{group}'",
                        guild.create_text_channel(
                            text_name, category=category, topic=topic
                        ),
                    )
                    text = await _on(
                        f"channel #{text_name} ({text.id}): syncing permissions",
                        text.edit(sync_permissions=True),
                    ) or text
                    text_channels[text_name] = text
                elif text.category_id != category.id or not text.permissions_synced:
                    text = await _on(
                        f"channel #{text_name} ({text.id}): moving/syncing to category '{group}'",
                        text.edit(category=category, sync_permissions=True),
                    ) or text
                    text_channels[text_name] = text

        expected_names = [
            name
            for region in ordered_regions
            for name, _ in channel_specs(region, county_channels, fully_overridden)
        ]
        expected_set = set(expected_names)
        current_names = [
            text.name
            for text in sorted(guild.text_channels, key=lambda item: (item.position, item.id))
            if text.category_id == category.id and text.name in expected_set
        ]
        if current_names != expected_names:
            for name in expected_names:
                text = text_channels[name]
                if moves_applied:
                    await asyncio.sleep(move_delay_seconds)
                await _on(
                    f"channel #{name} ({text.id}): reordering",
                    text.move(end=True, category=category),
                )
                moves_applied += 1


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create and order regional Discord channels."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Apply the region setup to Discord"
    )
    args = parser.parse_args()
    if not args.apply:
        parser.error("This job changes Discord channels; pass --apply to run it.")

    load_dotenv(ROOT / ".env")
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        parser.error("DISCORD_TOKEN is missing; set it in .env")
    try:
        alert_forum_id = int(os.environ["DISCORD_CHANNEL_ID"])
        move_delay = float(os.getenv("DISCORD_CHANNEL_MOVE_DELAY_SECONDS", "3"))
    except (KeyError, ValueError):
        parser.error("DISCORD_CHANNEL_ID and a valid move delay must be set in .env")
    if move_delay < 0:
        parser.error("DISCORD_CHANNEL_MOVE_DELAY_SECONDS cannot be negative")

    try:
        regions, region_groups = load_region_config()
        county_channels, fully_overridden = load_county_overrides(regions)
    except (OSError, SyntaxError, ValueError) as error:
        parser.error(f"Could not load region definitions from bot.py: {error}")

    class RegionSetupClient(discord.Client):
        def __init__(self):
            super().__init__(intents=discord.Intents.default())
            self.exit_code = 0
            self.setup_started = False

        async def on_ready(self):
            if self.setup_started:
                return
            self.setup_started = True
            try:
                alert_forum = (
                    self.get_channel(alert_forum_id)
                    or await _on(
                        f"alert forum ({alert_forum_id}): fetching",
                        self.fetch_channel(alert_forum_id),
                    )
                )
                if not isinstance(alert_forum, discord.ForumChannel):
                    print(f"Channel {alert_forum_id} is not a forum channel.")
                    self.exit_code = 1
                    return

                permissions = alert_forum.guild.me.guild_permissions
                missing = [
                    name for name in ("manage_channels", "manage_roles")
                    if not getattr(permissions, name)
                ]
                if missing:
                    invite = discord.utils.oauth_url(
                        self.user.id,
                        permissions=discord.Permissions(
                            manage_channels=True, manage_roles=True
                        ),
                        scopes=("bot",),
                    )
                    print(
                        "Missing permissions for regional setup: "
                        f"{', '.join(missing)}. Re-authorize with: {invite}"
                    )
                    self.exit_code = 1
                    return

                await ensure_region_tags(alert_forum, regions)
                await ensure_region_channels(
                    alert_forum, region_groups, county_channels, fully_overridden, move_delay
                )
                print("Regional tags, channels, category permissions, and ordering are up to date.")
            except discord.HTTPException as error:
                print(f"Regional setup failed: {error}")
                print(f"Failed target: {getattr(error, 'target', 'unknown')}")
                if error.code == 50001:
                    print(
                        "The bot lacks channel-level access (View Channel, Manage Channels, "
                        "Manage Permissions) on the alert forum or an existing region "
                        "category/forum/banter channel. Check overwrites that deny the bot "
                        "or its role, or grant it Administrator."
                    )
                self.exit_code = 1
            finally:
                await self.close()

    client = RegionSetupClient()
    try:
        await client.start(token)
    except discord.LoginFailure:
        print("Discord rejected DISCORD_TOKEN.")
        return 1
    return client.exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))