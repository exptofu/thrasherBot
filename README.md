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

Georgia's 159 counties are grouped into 20 regions in the `REGIONS` dict in `bot.py`. The bot:

- Creates a forum tag for each region in the `DISCORD_CHANNEL_ID` forum on startup and tags each new post with its county's region. Discord allows 20 tags per forum, so the region list uses all of them.
- Creates a forum channel named after each region (in the same category) for discussion, where members can reply but only the bot starts posts.
- Posts to each region's `<region>_rba` post when a net-new sighting appears, linking to the original post.

The bot needs the Manage Channels and Manage Threads permissions; the invite link it logs on a permission error includes them.

## Region map

```powershell
python georgia_map.py
```

Writes `georgia_regions.svg`, a dark-background county map colored by region with a legend ordered north to south. County outlines are downloaded once from the public plotly/datasets GeoJSON and cached in `.cache/`. Region colors are in `COLORS` in `georgia_map.py`; update them when `REGIONS` changes.