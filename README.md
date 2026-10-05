# Thrasher Bot

A Discord bot that posts notable eBird sightings to a forum channel.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `EBIRD_API_KEY`, `DISCORD_TOKEN`, and `DISCORD_CHANNEL_ID` in `.env`. The channel must be a Discord forum channel. Then run:

```powershell
python bot.py
```

## Regions

Georgia's 159 counties are grouped into 16 regions in the `REGIONS` dict in `bot.py`. The bot:

- Tags each new alert post with its county's region.
- Posts a link to the county's `<region>-chat` text channel when a net-new sighting appears. Rare-bird sightings are also linked in `state-wide-rarities`.

The bot needs View Channel, Send Messages, Send Messages in Threads, Read Message History, and Manage Threads in the alert forum. Its invite link on a permission error includes these permissions.

## Regional setup

Regional channels are managed separately from bot startup. Run this job to add missing tags, create or move channels, sync category permissions, and order categories and chats:

```powershell
python utils/region_channels.py --apply
```

The job reads `REGIONS` and `REGION_GROUPS` from `bot.py` without starting the bot. It places the configured categories immediately after the existing `Discussions` category, in `REGION_GROUPS` order. Each category gets a `<category>-rba` forum, followed by its alphabetized `<region>-chat` text channels. It requires Manage Channels and Manage Roles, does not delete obsolete tags or channels, and waits `DISCORD_CHANNEL_MOVE_DELAY_SECONDS` between channel moves (default: 3 seconds). Remove retired forum tags manually before applying if the forum is at Discord's 20-tag limit. If an existing channel has the wrong type, rename or archive it before rerunning setup. Previously created category-chat channels are left in place and can be archived or deleted manually.

### Temporary permission sync utility

`utils/sync_category_permissions.py` previews channels whose permissions differ from their parent category. Review the preview, then add `--apply` to sync them. It skips the forum configured by `DISCORD_CHANNEL_ID`, but applies to every other categorized channel in that guild, not only regional channels. Syncing replaces each affected channel's custom overwrites with its category's permissions.

```powershell
python utils/sync_category_permissions.py
python utils/sync_category_permissions.py --apply
```

## Region map

```powershell
python georgia_map.py
```

Writes `georgia_regions.svg`, a dark-background county map with two stacked panels, each with its own legend ordered north to south: categories on top and regions below. County outlines are downloaded once from the public plotly/datasets GeoJSON and cached in `.cache/`. Region colors are in `COLORS` and category colors in `GROUP_COLORS` in `georgia_map.py`; update them when the regions or categories change.

`georgia_map.py` renders the current `REGIONS` and `REGION_GROUPS` layout. Keep those definitions synchronized with `bot.py`. The current category assignment and Discord migration notes are in [docs/regions.md](docs/regions.md).