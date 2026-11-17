# Region Data and Map Generation

## Shared Source of Truth

`regions.json` is the canonical county-to-region configuration for the bot, map
generator, and Pages app. County records use five-digit Census GEOIDs, so county
names shared by different states cannot collide. Each region stores its counties
as `{ "geoid": "13001", "name": "Appling" }` records; category membership,
labels, and colors are in `metadata`.

The Python bot and SVG generator load this file through `region_data.py`. The
website in `site/` fetches the same JSON and matches county geometry by GEOID.
There is no longer a separate region list to sync into JavaScript.

When changing regions or adding counties:

1. Edit `regions.json`. Use five-digit GEOIDs and preserve each county's display
   name. Add a new region to exactly one `metadata.region_groups` category and
   give it a `metadata.region_labels` entry.
2. Verify the shared data and generate the SVG:
   ```powershell
   python -c "from region_data import COUNTY_REGION; print(f'Validated {len(COUNTY_REGION)} county GEOIDs')"
   python georgia_map.py
   ```
3. Export the PNG at 200 DPI if needed:
   ```powershell
   & "C:\Program Files\Inkscape\bin\inkscape.exe" .\georgia_regions.svg -o georgia_regions.png --export-dpi=200
   ```

`region_data.py` rejects duplicate/invalid GEOIDs and incomplete category
assignments. The map generator also checks that every configured GEOID exists
in the downloaded county GeoJSON.

## Out-of-State Counties

The current out-of-state counties are:

- Greater Augusta: Aiken (`45003`) and Edgefield (`45037`), South Carolina
- Greater Columbus: Russell (`01113`), Alabama

The SVG uses a striped fill for any configured county whose GEOID is not in
Georgia (`13`). Add another county by adding its GEOID and name to the relevant
region in `regions.json`; no state-specific code changes are needed.

## GitHub Pages Deployment

The Pages source files are in `site/`. The `Deploy Pages` GitHub Actions workflow
copies `regions.json` into the Pages artifact and deploys it when the site or
shared region data changes on `master`. Configure **Settings → Pages → Build
and deployment → Source → GitHub Actions** once; the `gh-pages` branch is no
longer used for deployments.
