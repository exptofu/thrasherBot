# Project guidance

- `bot.py` polls eBird for notable sightings and posts grouped sightings to a Discord forum; SQLite stores state.
- Keep changes focused and follow the existing single-file structure unless a feature clearly needs a separate module.
- Read configuration from environment variables. Never commit credentials; update `.env.example` when configuration changes.
- Preserve API request pacing/retries and take care with SQLite schema changes, since the database may contain live bot state.
- Dependencies belong in `requirements.txt`. Avoid adding a dependency for behavior the standard library already handles.
- There is no test suite yet. For Python edits, run `python -m py_compile bot.py` and add or run a focused behavior check when practical.