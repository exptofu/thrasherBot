# Map Generation

The `georgia_map.py` script generates both SVG and PNG visualizations of the Georgia regions configuration.

## Generating the Map

After updating region configurations in `REGIONS`, `REGION_LABELS`, or `REGION_GROUPS`:

1. **Generate SVG from region data:**
   ```powershell
   python georgia_map.py
   ```
   This produces `georgia_regions.svg` with all 23 regions and out-of-state border counties.

2. **Convert SVG to PNG at 200 DPI using Inkscape:**
   ```powershell
   & "C:\Program Files\Inkscape\bin\inkscape.exe" .\georgia_regions.svg -o georgia_regions.png --export-dpi=200
   ```

Both steps are required when region definitions change.

## Out-of-State Counties

Some regions include counties from neighboring states to better represent birding areas:
- **Greater Augusta**: Aiken and Edgefield counties (South Carolina)
- **Greater Columbus**: Russell County (Alabama)

These out-of-state counties are rendered with:
- A diagonal striped pattern fill (darker lines at -45°) to visually distinguish them from Georgia counties
- Thin internal borders (no thick white edge)
- A thick white border on the Georgia side of the state boundary

This makes the Georgia border explicit while still showing the regional coverage.

## SVG Structure

The generated `georgia_regions.svg` includes:
- **Defs**: A diagonal stripe pattern (`oos-stripes`) applied to out-of-state counties
- **County paths**: Colored by region, with striped pattern overlay for out-of-state counties
- **State boundary**: Thick white border (3.2px) on all external GA edges and state boundaries
- **Region labels**: Center-of-mass text labels with black outline for readability
- **Legend**: RBA category colors positioned on the right side

## Coordinates and Scaling

The map uses:
- **GeoJSON source**: Public plotly/datasets US counties with FIPS codes
- **Georgia FIPS code**: "13"
- **South Carolina FIPS code**: "45" (Aiken, Edgefield)
- **Alabama FIPS code**: "01" (Russell)
- **Map width**: 700px (configurable `MAP_WIDTH`)
- **Padding**: 40px on all sides
- **Legend position**: Far right (MAP_WIDTH + PAD + 20)

## Syncing Regions

Keep the following synchronized across files:
- `bot.py`: `REGIONS`, `REGION_GROUPS`, `REGION_LABELS`
- `georgia_map.py`: `REGIONS`, `REGION_LABELS`, `REGION_GROUPS`, `GROUP_COLORS`

The `load_counties()` function loads only Georgia counties plus the configured out-of-state counties (Aiken, Edgefield, Russell). All other counties are excluded.
