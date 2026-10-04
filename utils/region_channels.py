"""Create, sync, and order regional Discord channels."""
import asyncio

import discord


async def ensure_region_tags(channel: discord.ForumChannel, regions: dict[str, list[str]]):
    have = {tag.name for tag in channel.available_tags}
    missing = [region for region in regions if region not in have]
    if missing:
        await channel.edit(
            available_tags=[
                *channel.available_tags,
                *(discord.ForumTag(name=region) for region in missing),
            ]
        )


async def ensure_region_forums(
    channel: discord.ForumChannel,
    region_groups: dict[str, list[str]],
    move_delay_seconds: float,
):
    """Create and group regional discussion forums and banter channels."""
    guild = channel.guild
    forums = {forum.name: forum for forum in guild.forums}
    text_channels = {text.name: text for text in guild.text_channels}
    categories = {category.name: category for category in guild.categories}
    moves_applied = 0
    for group, regions in region_groups.items():
        category = categories.get(group)
        if category is None:
            category = await guild.create_category(group)
            categories[group] = category
        ordered_regions = sorted(regions)
        for region in ordered_regions:
            forum = forums.get(region)
            if forum is None:
                forum = await guild.create_forum(
                    region,
                    category=category,
                    topic=f"New sightings and discussion for {region}",
                )
                forum = await forum.edit(sync_permissions=True) or forum
                forums[region] = forum
            elif forum.category_id != category.id or not forum.permissions_synced:
                forum = await forum.edit(category=category, sync_permissions=True) or forum
                forums[region] = forum

            text_name = f"{region}-banter"
            text = text_channels.get(text_name)
            if text is None:
                text = await guild.create_text_channel(
                    text_name,
                    category=category,
                    topic=f"General discussion for {region}",
                )
                text = await text.edit(sync_permissions=True) or text
                text_channels[text_name] = text
            elif text.category_id != category.id or not text.permissions_synced:
                text = await text.edit(category=category, sync_permissions=True) or text
                text_channels[text_name] = text

        expected_names = [
            name
            for region in ordered_regions
            for name in (region, f"{region}-banter")
        ]
        expected_set = set(expected_names)
        current_names = [
            text.name
            for text in sorted(guild.channels, key=lambda item: (item.position, item.id))
            if text.category_id == category.id and text.name in expected_set
        ]
        pairs_are_adjacent = all(
            text_channels[f"{region}-banter"].position == forums[region].position + 1
            for region in ordered_regions
        )
        if current_names != expected_names or not pairs_are_adjacent:
            for region in ordered_regions:
                forum = forums[region]
                text = text_channels[f"{region}-banter"]
                if moves_applied:
                    await asyncio.sleep(move_delay_seconds)
                await forum.move(end=True, category=category)
                moves_applied += 1
                await asyncio.sleep(move_delay_seconds)
                await text.move(after=forum)
                moves_applied += 1