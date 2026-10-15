# Regions and Categories

`REGIONS` and `REGION_GROUPS` in `bot.py` are the bot's county-to-region and region-to-category configuration. Keep the matching definitions and `REGION_LABELS`/`COLORS` in `georgia_map.py` synchronized with them. All 159 counties must appear once, and every region must belong to exactly one category. The 16 region tags stay below Discord's 20-tag forum limit.

| Category | Regions |
|---|---|
| Metro Atlanta | Metro Atlanta North, Metro Atlanta South, Fulton County, Dekalb County, Gwinnett County |
| Southeast Georgia | Golden Isles |
| Savannah Area | Greater Savannah Area |
| Athens Area | Greater Athens Area |
| Augusta Area | Greater Augusta Area |
| Central Georgia | Macon, Fall Line Sandhills |
| West Georgia | West Piedmont, Columbus Area |
| North Georgia | North Georgia Mountains, Broad River Watershed |
| South Georgia | Inland Coastal Plain |

## Discord Channels

The standalone `utils/region_channels.py` job creates and orders channels; it does not run on bot startup. It places the configured categories immediately after the existing `Discussions` category, following `REGION_GROUPS` order. Each category gets a `<category>-rba` forum for RBA discussion. Each region gets a `<region>-chat` text channel for discussion and bot sighting links. Within each category, channel order is category RBA followed by region chats alphabetically.

Run the setup after reviewing the region and category configuration:

```powershell
python -m py_compile bot.py utils/region_channels.py utils/county_table.py georgia_map.py
python georgia_map.py
python utils/region_channels.py --apply
```

The setup adds missing forum tags and creates or moves the configured channels, syncing their permissions to the parent category. If a managed channel exists with the wrong type, rename or archive it and rerun setup; the job does not delete obsolete forum tags, categories, or text channels. Category-chat channels created by an earlier setup are left untouched and may be archived or deleted manually. Remove retired forum tags manually before applying if the forum is at Discord's 20-tag limit. Existing sighting posts and threads are not retagged or redistributed.

`utils/sync_category_permissions.py` is a separate preview-first utility that applies category permissions to all categorized channels in the guild except the forum ID in `DISCORD_CHANNEL_ID`; it is not limited to regional channels. Review its complete preview before using `--apply`, since affected channel-specific overwrites are replaced by category permissions.