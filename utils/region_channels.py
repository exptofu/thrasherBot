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


def channel_slug(name: str) -> str:
    return name.lower().replace(" ", "-")


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


def category_channel_specs(category: str, regions: list[str]) -> list[tuple[str, str, bool]]:
    """Channel (name, topic, is_forum) specs in category discussion order."""
    specs = [(f"{channel_slug(category)}-rba", f"RBA discussion for {category}", True)]
    specs.extend(
        (f"{region}-chat", f"General birding discussion for {region.replace('-', ' ')}", False)
        for region in sorted(regions)
    )
    return specs


async def ensure_region_channels(
    channel: discord.ForumChannel,
    region_groups: dict[str, list[str]],
    move_delay_seconds: float,
):
    """Create, permission-sync, and order category and regional discussion channels."""
    guild = channel.guild
    managed_channels = {
        item.name: item
        for item in guild.channels
        if not isinstance(item, discord.CategoryChannel)
    }
    categories = {category.name: category for category in guild.categories}
    discussion_category = next(
        (category for category in categories.values() if category.name.casefold() == "discussions"),
        None,
    )
    if discussion_category is None:
        raise ValueError("Discord category 'Discussions' was not found; no region channels were changed.")
    moves_applied = 0
    for group, regions in region_groups.items():
        category = categories.get(group)
        if category is None:
            category = await _on(f"creating category '{group}'", guild.create_category(group))
            categories[group] = category
        for channel_name, topic, is_forum in category_channel_specs(group, regions):
            managed_channel = managed_channels.get(channel_name)
            if managed_channel is not None:
                is_expected_type = (
                    isinstance(managed_channel, discord.ForumChannel)
                    if is_forum
                    else isinstance(managed_channel, discord.TextChannel)
                )
                if not is_expected_type:
                    expected_type = "forum" if is_forum else "text"
                    actual_type = "forum" if isinstance(managed_channel, discord.ForumChannel) else "text"
                    raise ValueError(
                        f"#{channel_name} is currently a {actual_type} channel, but must be a "
                        f"{expected_type} channel. Rename or archive it, then rerun this job."
                    )
            else:
                create_channel = guild.create_forum if is_forum else guild.create_text_channel
                managed_channel = await _on(
                    f"creating {'forum' if is_forum else 'text'} channel '{channel_name}' in category '{group}'",
                    create_channel(channel_name, category=category, topic=topic),
                )
                managed_channels[channel_name] = managed_channel

            if managed_channel.category_id != category.id or not managed_channel.permissions_synced:
                managed_channel = await _on(
                    f"channel #{channel_name} ({managed_channel.id}): moving/syncing to category '{group}'",
                    managed_channel.edit(category=category, sync_permissions=True),
                ) or managed_channel
                managed_channels[channel_name] = managed_channel

    current_category_order = [
        category.name
        for category in sorted(categories.values(), key=lambda item: (item.position, item.id))
    ]
    region_category_names = list(region_groups)
    final_category_order = [
        name for name in current_category_order if name not in region_category_names
    ]
    discussion_index = final_category_order.index(discussion_category.name)
    final_category_order[discussion_index + 1:discussion_index + 1] = region_category_names
    for group in region_category_names:
        category = categories[group]
        position = final_category_order.index(group)
        if category.position != position:
            await _on(
                f"category '{group}': reordering",
                category.edit(position=position),
            )

    for group, regions in region_groups.items():
        category = categories[group]
        expected_names = [name for name, _, _ in category_channel_specs(group, regions)]
        expected_set = set(expected_names)
        current_names = [
            item.name
            for item in sorted(guild.channels, key=lambda item: (item.position, item.id))
            if item.name in expected_set and getattr(item, "category_id", None) == category.id
        ]
        if current_names != expected_names:
            for name in expected_names:
                item = managed_channels[name]
                if moves_applied:
                    await asyncio.sleep(move_delay_seconds)
                await _on(
                    f"channel #{name} ({item.id}): reordering",
                    item.move(end=True, category=category),
                )
                moves_applied += 1


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create and order regional Discord channels.")
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
                    alert_forum, region_groups, move_delay
                )
                print("Regional tags, channels, category permissions, and ordering are up to date.")
            except ValueError as error:
                print(f"Regional setup failed: {error}")
                self.exit_code = 1
            except discord.HTTPException as error:
                print(f"Regional setup failed: {error}")
                print(f"Failed target: {getattr(error, 'target', 'unknown')}")
                if error.code == 50001:
                    print(
                        "The bot lacks channel-level access (View Channel, Manage Channels, "
                        "Manage Permissions) on the alert forum or an existing category "
                        "or regional chat channel. Check overwrites that deny the bot "
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