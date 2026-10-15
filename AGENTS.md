# Project guidance

- `bot.py` polls eBird for notable sightings and posts grouped sightings to a Discord forum; SQLite stores state.
- `REGIONS` in `bot.py` maps every Georgia county to one of at most 20 regions (Discord's forum tag limit); each region is a forum tag and a discussion forum with a `<region>_rba` post. Keep all 159 counties assigned once, and update `COLORS` in `georgia_map.py` when regions change.
- `georgia_map.py` renders `georgia_regions.svg` using only the standard library; it reads `REGIONS` from `bot.py` by parsing it, so keep `REGIONS` a plain literal.
- Keep changes focused and follow the existing single-file structure unless a feature clearly needs a separate module.
- Read configuration from environment variables. Never commit credentials; update `.env.example` when configuration changes.
- Preserve API request pacing/retries and take care with SQLite schema changes, since the database may contain live bot state.
- Dependencies belong in `requirements.txt`. Avoid adding a dependency for behavior the standard library already handles.
- There is no test suite yet. For Python edits, run `python -m py_compile bot.py georgia_map.py` and add or run a focused behavior check when practical.