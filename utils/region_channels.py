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
MAP_CONFIG_PATH = ROOT / "georgia_map.py"


def _literal_assignments(names: set[str], source_path: Path) -> dict:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in names):
            found[node.targets[0].id] = ast.literal_eval(node.value)
    if set(found) != names:
        raise ValueError(f"{source_path.name} must define literal {', '.join(sorted(names))}")
    return found


def load_region_config() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Read the canonical region definitions from georgia_map.py without importing the bot."""
    config = _literal_assignments({"REGIONS", "REGION_GROUPS"}, MAP_CONFIG_PATH)
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


async def ensure_region_tags(channel: discord.ForumChannel, region_groups: dict[str, list[str]]):
    """Create category tags for the alert forum while leaving the region chat routing unchanged."""
    have = {tag.name for tag in channel.available_tags}
    missing = [category for category in region_groups if category not in have]
    if missing:
        await _on(
            f"alert forum #{channel.name} ({channel.id}): adding tags",
            channel.edit(
                available_tags=[
                    *channel.available_tags,
                    *(discord.ForumTag(name=category) for category in missing),
                ]
            ),
        )


def rba_forum_name(category: str, regions: list[str]) -> str:
    if len(regions) == 1:
        return f"{channel_slug(regions[0])}-rba"
    return f"{channel_slug(category)}-rba"


def category_channel_specs(category: str, regions: list[str]) -> list[tuple[str, str, bool]]:
    """Channel (name, topic, is_forum) specs in category discussion order."""
    specs = [(rba_forum_name(category, regions), f"RBA discussion for {category}", True)]
    specs.extend(
        (f"{region}-chat", f"General birding discussion for {region.replace('-', ' ')}", False)
        for region in sorted(regions)
    )
    return specs


def rba_guidelines_for_regions(regions: list[str]) -> str:
    bullets = "\n".join(f"* {name.replace('-', ' ').title()}" for name in sorted(regions))
    return (
        "This is the rare bird alert page for the following regions:\n"
        f"{bullets}\n\n"
        "Birds marked in eBird as R (rare) are suitable for posting in this forum. If you are unsure, please post your sighting in a more regional chat.\n\n"
        "All posts should be titled: Species Name-Site Location Name (County)-Month/Day/Year\n\n"
        "Posts should include the full species name, location including county, and any other pertinent information.\n\n"
        "All replies and follow up comments are welcome, but MUST BE IN THE FORUM topic or may be deleted by an admin or moderator.\n\n"
        "You can manage notifications on individual topics. By default, notifications are set to @mentions."
    )


async def ensure_pinned_rba_guidelines(guild: discord.Guild, region_groups: dict[str, list[str]]) -> None:
    """Create or update only the bot-owned pinned guidance thread in each category RBA forum."""
    bot_user_id = guild.me.id if guild.me else None
    for category, regions in region_groups.items():
        forum_name = rba_forum_name(category, regions)
        forum = discord.utils.get(guild.channels, name=forum_name)
        if not isinstance(forum, discord.ForumChannel):
            continue
        title = "‼️READ BEFORE POSTING - Guidelines"
        content = rba_guidelines_for_regions(regions)
        try:
            existing = None
            async for thread in forum.archived_threads(limit=100):
                if getattr(thread, "owner_id", None) == bot_user_id:
                    existing = thread
                    break
            if existing is None:
                for thread in getattr(forum, "threads", []):
                    if getattr(thread, "owner_id", None) == bot_user_id and thread.name == title:
                        existing = thread
                        break
            if existing is None:
                created = await forum.create_thread(name=title, content=content)
                edit_method = getattr(created, "edit", None)
                if callable(edit_method):
                    try:
                        await edit_method(pinned=True)
                    except discord.HTTPException as error:
                        print(f"Guidance thread created for {forum_name}, but pinning failed: {error}")
                continue
            await existing.edit(name=title)
            if getattr(existing, "pinned", False) is False:
                try:
                    await existing.edit(pinned=True)
                except discord.HTTPException as error:
                    print(f"Guidance thread in {forum_name} was found but could not be pinned: {error}")
            starter_message = getattr(existing, "starter_message", None)
            if starter_message is None:
                try:
                    starter_message = await existing.fetch_message(existing.id)
                except (AttributeError, discord.HTTPException):
                    starter_message = None
            if starter_message is not None:
                try:
                    await starter_message.edit(content=content)
                except discord.HTTPException as error:
                    print(f"Guidance post content update failed for {forum_name}: {error}")
            else:
                print(
                    f"Guidance thread already exists for {forum_name}, but its starter message could not be loaded; "
                    "skipping duplicate post creation."
                )
        except discord.HTTPException as error:
            print(f"Skipping pinned guidance setup for {forum_name}: {error}")
        except Exception as error:  # pragma: no cover - safeguard for unexpected SDK edge cases.
            print(f"Unexpected error while handling {forum_name}: {error!r}")


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


def preview_category_plan(region_groups: dict[str, list[str]]) -> None:
    """Print categories and channel names that would be created or reordered."""
    print("Planned categories and channels:")
    for category, regions in region_groups.items():
        print(f"- Category: {category}")
        for name, _, is_forum in category_channel_specs(category, regions):
            kind = "forum" if is_forum else "text"
            print(f"  - {kind}: {name}")


def planned_channel_names(region_groups: dict[str, list[str]]) -> list[str]:
    planned = []
    for category, regions in region_groups.items():
        if category not in planned:
            planned.append(category)
        planned.extend(name for name, _, _ in category_channel_specs(category, regions))
    return planned


async def diff_live_channels(guild: discord.Guild, region_groups: dict[str, list[str]]) -> None:
    """Print any category/channel names that are missing or extra compared to the planned setup."""
    planned_names = planned_channel_names(region_groups)
    planned_set = set(planned_names)
    live = {
        item.name
        for item in guild.channels
        if isinstance(item, (discord.CategoryChannel, discord.TextChannel, discord.ForumChannel))
    }
    missing = [name for name in planned_names if name not in live]
    extra = sorted(live - planned_set)
    print("Discord vs planned region setup:")
    if missing:
        print("Missing in Discord:")
        for name in missing:
            print(f"  - {name}")
    else:
        print("Missing in Discord: none")
    if extra:
        print("Extra in Discord:")
        for name in extra:
            print(f"  - {name}")
    else:
        print("Extra in Discord: none")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create and order regional Discord channels.")
    parser.add_argument(
        "--apply", action="store_true", help="Apply the region setup to Discord"
    )
    parser.add_argument(
        "--diff", action="store_true", help="Compare the live guild to the planned region setup without changing anything"
    )
    args = parser.parse_args()

    try:
        regions, region_groups = load_region_config()
    except (OSError, SyntaxError, ValueError) as error:
        parser.error(f"Could not load region definitions from georgia_map.py: {error}")

    if not args.apply and not args.diff:
        preview_category_plan(region_groups)
        print("Preview only; no Discord changes were made. Pass --apply to create and reorder the channels.")
        return 0

    if args.diff:
        load_dotenv(ROOT / ".env")
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            parser.error("DISCORD_TOKEN is missing; set it in .env")
        try:
            alert_forum_id = int(os.environ["DISCORD_CHANNEL_ID"])
        except (KeyError, ValueError):
            parser.error("DISCORD_CHANNEL_ID must be set in .env")

        class DiffClient(discord.Client):
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
                    await diff_live_channels(alert_forum.guild, region_groups)
                except discord.HTTPException as error:
                    print(f"Discord diff failed: {error}")
                    self.exit_code = 1
                finally:
                    await self.close()

        client = DiffClient()
        try:
            await client.start(token)
        except discord.LoginFailure:
            print("Discord rejected DISCORD_TOKEN.")
            return 1
        return client.exit_code

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

                await ensure_region_tags(alert_forum, region_groups)
                await ensure_region_channels(
                    alert_forum, region_groups, move_delay
                )
                print('Finished ordering')
                await ensure_pinned_rba_guidelines(alert_forum.guild, region_groups)
                print("Regional tags, channels, category permissions, ordering, and pinned guidance posts are up to date.")
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