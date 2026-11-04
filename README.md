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

## Deployment version

On startup the bot records `bot_version`, `bot_source_hash` (SHA-256 of `bot.py`), and `bot_started_at` in the `meta` table of `sightings.db`. Query it on the VPC or a synced copy:

```powershell
sqlite3 sightings.db "SELECT key, value FROM meta;"
```

Compare `bot_source_hash` with `sha256sum bot.py` on the server to confirm it is running the same source as the working copy.

## Regions

Georgia's 159 counties are grouped into 16 regions in the `REGIONS` dict in `bot.py`. The bot:

- Tags each new alert post with its county's region.
- Posts a link to the county's `<region>-chat` text channel when a net-new sighting appears. Rare-bird sightings are also linked in `state-wide-rarities`.
- Archives a species/location RBA post once its newest matching sighting is more than `EBIRD_BACK_DAYS * 2` days old. Activity is measured from the newest sighting, so a post with an old first report stays open while birds are still being found there.

The bot needs View Channel, Send Messages, Send Messages in Threads, Read Message History, and Manage Threads in the alert forum. Its invite link on a permission error includes these permissions.

## Checklist location edits

Each species/checklist message is tracked in the `groups` table together with the thread it was posted in. If a submitter edits an eBird checklist's location after the bot has posted it, the bot treats the sighting as moved:

- The stale message is deleted and reposted in the thread for the corrected hotspot or county.
- If the stale message is the thread starter (its message ID equals the thread ID), it is kept and its embed is edited to say the sighting moved, with a link to the updated post. Deleting a forum starter would delete the whole thread and any other checklists posted there.

Existing databases get the `groups.thread_id` column added automatically with `ALTER TABLE` and backfilled from `posts`; no schema reset or data loss is needed.

## No longer in RBA / removed

The notable feed is not a complete index and can omit a record for a poll. After `MISSING_POLLS` consecutive misses (default 3), the bot checks the checklist view once:

- Species still listed and the sighting is unreviewed → `⚠️ No longer in RBA` (red).
- Species still listed and the sighting is already reviewed (confirmed or rejected) → keep its review status; reviewed records are not downgraded by feed omissions.
- Species no longer listed, or the checklist was deleted → `🗑️ Removed from checklist` (red).

If the sighting reappears, the counter and status are cleared. Sightings older than `EBIRD_BACK_DAYS` can no longer appear in the feed, so they keep their last status instead of being marked missing; already-labeled aged-out records are restored gradually. Lookup failures leave the post unchanged and retry next poll. Reviewed records are only re-checked once per absence, and a one-time backlog of older labels is processed gradually. Feed rows are deduplicated by checklist + species (rich-media observations arrive once per photo), and the last good feed size is stored as `meta.last_feed_size`. If a poll comes in more than 30% smaller, the bot merges up to two retries and pauses missing-status updates when the response still looks short; the first poll after startup also pauses them while it captures a baseline.

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

### Manual archive backfill

`utils/archive_orphaned_posts.py` archives threads the bot created in the alert forum whose sightings are no longer in `sightings.db`. The bot's automatic archive pass can only see posts that still have database rows, so these threads are otherwise left open forever. Member-created posts are never touched, and pinned posts are skipped unless `--include-pinned` is passed. Preview, then apply:

```powershell
python utils/archive_orphaned_posts.py
python utils/archive_orphaned_posts.py --apply
```

It opens the database read-only, needs Manage Threads, and leaves a thread open when its newest stored sighting or its last message is inside `EBIRD_BACK_DAYS * 2` days. `--days` overrides the window, `--db` points at another database file, `--allow-empty-posts` permits `--apply` when the `posts` table is empty (for example after a schema reset), and `--include-pinned` also archives pinned bot posts.

## Region map

```powershell
python georgia_map.py
```

Writes `georgia_regions.svg`, a dark-background county map with two stacked panels, each with its own legend ordered north to south: categories on top and regions below. County outlines are downloaded once from the public plotly/datasets GeoJSON and cached in `.cache/`. Region colors are in `COLORS` and category colors in `GROUP_COLORS` in `georgia_map.py`; update them when the regions or categories change.

`georgia_map.py` renders the current `REGIONS` and `REGION_GROUPS` layout. Keep those definitions synchronized with `bot.py`. The current category assignment and Discord migration notes are in [docs/regions.md](docs/regions.md).