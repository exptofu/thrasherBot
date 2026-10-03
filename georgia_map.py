"""Render georgia_regions.svg: Georgia counties colored by the REGIONS grouping in bot.py.

Stdlib only. County outlines come from the public plotly/datasets GeoJSON (Census data).
Usage: python georgia_map.py [output.svg]
"""
import ast
import json
import math
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
GEORGIA_FIPS = "13"
MAP_WIDTH = 620
PAD = 40
LEGEND_WIDTH = 230

# Brightest color = most eBird activity; listed in that order.
COLORS = {
    "dekalb": "#fffac8", "fulton": "#aaffc3", "glynn-camden": "#ffd8b1", "cobb": "#ffe119",
    "central-georgia": "#bfef45", "clarke-oconee": "#fabed4", "metro-atlanta-south": "#dcbeff",
    "northwest-georgia": "#42d4f4", "chatham": "#a9a9a9", "east-georgia": "#f58231",
    "gwinnett": "#3cb44b", "northeast-mountains": "#469990", "west-georgia": "#808000",
    "southwest-georgia": "#9A6324", "metro-atlanta-east": "#f032e6", "cherokee-forsyth": "#4363d8",
    "north-central-mountains": "#e6194B", "coastal-georgia-other": "#911eb4",
    "south-central-georgia": "#800000", "southeast-georgia": "#000075",
}


def load_regions() -> dict[str, list[str]]:
    # Parse bot.py instead of importing it, which needs env vars and opens the database.
    tree = ast.parse((Path(__file__).parent / "bot.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "REGIONS":
            return ast.literal_eval(node.value)
    raise SystemExit("REGIONS not found in bot.py")


def load_counties() -> list[dict]:
    cache = Path(__file__).parent / ".cache" / "geojson-counties-fips.json"
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(GEOJSON_URL, cache)
    data = json.loads(cache.read_text(encoding="utf-8"))
    return [f for f in data["features"] if f["properties"]["STATE"] == GEORGIA_FIPS]


def rings(geometry: dict):
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for poly in polys:
        yield from poly


def main(out: Path):
    regions = load_regions()
    county_region = {c.lower(): r for r, cs in regions.items() for c in cs}
    features = load_counties()

    names = {f["properties"]["NAME"].lower() for f in features}
    if names != set(county_region):
        raise SystemExit(f"County mismatch: {sorted(names ^ set(county_region))}")
    missing = [r for r in regions if r not in COLORS]
    if missing:
        raise SystemExit(f"Add colors for: {missing}")

    lons = [p[0] for f in features for r in rings(f["geometry"]) for p in r]
    lats = [p[1] for f in features for r in rings(f["geometry"]) for p in r]
    kx = math.cos(math.radians((min(lats) + max(lats)) / 2))
    min_x, max_y = min(lons) * kx, max(lats)
    scale = MAP_WIDTH / (max(lons) * kx - min_x)
    height = round((max_y - min(lats)) * scale) + 2 * PAD

    def project(p):
        return (p[0] * kx - min_x) * scale + PAD, (max_y - p[1]) * scale + PAD

    paths = []
    for f in sorted(features, key=lambda f: f["properties"]["NAME"]):
        name = f["properties"]["NAME"]
        region = county_region[name.lower()]
        projected = [[project(p) for p in r] for r in rings(f["geometry"])]
        d = " ".join(
            "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in r) + "Z" for r in projected
        )
        paths.append(
            f'<path d="{d}" fill="{COLORS[region]}"><title>{escape(name)} - {region}</title></path>'
        )

    region_lats: dict[str, list[float]] = {}
    for f in features:
        ys = [p[1] for r in rings(f["geometry"]) for p in r]
        region_lats.setdefault(county_region[f["properties"]["NAME"].lower()], []).append(
            (min(ys) + max(ys)) / 2
        )
    north_to_south = sorted(regions, key=lambda r: -sum(region_lats[r]) / len(region_lats[r]))

    legend = [
        f'<rect x="{PAD + MAP_WIDTH + 20}" y="{PAD + i * 22}" width="14" height="14" fill="{COLORS[r]}" '
        f'stroke="#fff" stroke-width="0.5"/>'
        f'<text x="{PAD + MAP_WIDTH + 42}" y="{PAD + 12 + i * 22}">{escape(r)}</text>'
        for i, r in enumerate(north_to_south)
    ]
    width = PAD + MAP_WIDTH + LEGEND_WIDTH
    full_height = max(height, 2 * PAD + len(legend) * 22)
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {full_height}" '
        f'width="{width}" font-family="sans-serif" font-size="13" fill="#fff">\n'
        f'<rect width="100%" height="100%" fill="#000"/>\n'
        f'<g stroke="#fff" stroke-width="0.6" stroke-linejoin="round">\n' + "\n".join(paths) + "\n</g>\n"
        + "\n".join(legend)
        + "\n</svg>\n",
        encoding="utf-8",
    )
    print(f"Wrote {out} ({len(features)} counties, {len(legend)} regions)")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "georgia_regions.svg"))
