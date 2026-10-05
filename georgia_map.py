"""Render georgia_regions.svg from the region/category layout used by the bot.

Stdlib only. County outlines come from the public plotly/datasets GeoJSON (Census data).
Usage: python georgia_map.py [output.svg]
"""
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
LEGEND_WIDTH = 380

# Keep these county assignments and categories synchronized with bot.py.
REGIONS = {
    "greater-athens-area": ["Barrow", "Walton", "Greene", "Morgan", "Oconee", "Oglethorpe", "Clarke", "Jackson", "Madison"],
    "greater-savannah-area": ["Chatham", "Bryan", "Liberty", "Effingham"],
    "gwinnett-county": ["Gwinnett"],
    "metro-atlanta-north": ["Cobb", "Forsyth", "Douglas", "Cherokee", "Hall", "Bartow", "Paulding"],
    "dekalb-county": ["DeKalb"],
    "metro-atlanta-south": ["Coweta", "Henry", "Rockdale", "Newton", "Clayton", "Fayette"],
    "macon": ["Bibb"],
    "fall-line-sandhills": [
        "Spalding", "Pike", "Upson", "Lamar", "Monroe", "Crawford", "Peach", "Houston", "Twiggs",
        "Jones", "Wilkinson", "Baldwin", "Butts", "Jasper", "Putnam", "Hancock", "Washington",
        "Dodge", "Pulaski", "Bleckley", "Laurens", "Johnson", "Taylor", "Macon", "Dooly", "Talbot",
        "Marion", "Schley", "Taliaferro", "Warren", "Glascock", "Emanuel",
    ],
    "west-piedmont": ["Carroll", "Heard", "Troup", "Meriwether", "Stewart", "Haralson", "Polk"],
    "north-georgia-mountains": [
        "Floyd", "Chattooga", "Walker", "Dade", "Catoosa", "Whitfield", "Gordon", "Murray", "Gilmer",
        "Pickens", "Dawson", "Union", "Fannin", "Lumpkin", "White", "Towns", "Rabun", "Habersham",
    ],
    "inland-coastal-plain": [
        "Irwin", "Ben Hill", "Lee", "Terrell", "Sumter", "Calhoun", "Webster", "Worth", "Crisp",
        "Colquitt", "Grady", "Thomas", "Brooks", "Lowndes", "Echols", "Clinch", "Charlton", "Ware",
        "Berrien", "Cook", "Lanier", "Atkinson", "Turner", "Tift", "Coffee", "Wilcox", "Telfair",
        "Wheeler", "Jeff Davis", "Appling", "Bacon", "Pierce", "Decatur", "Mitchell", "Baker", "Miller",
        "Seminole", "Early", "Clay", "Quitman", "Randolph", "Dougherty", "Toombs", "Montgomery",
        "Treutlen", "Tattnall", "Evans", "Candler", "Bulloch", "Screven",
    ],
    "broad-river-watershed": ["Elbert", "Hart", "Stephens", "Franklin", "Banks"],
    "columbus-area": ["Harris", "Muscogee", "Chattahoochee"],
    "golden-isles": ["Wayne", "Long", "McIntosh", "Glynn", "Brantley", "Camden"],
    "greater-augusta-area": ["Jenkins", "Burke", "Jefferson", "Richmond", "McDuffie", "Columbia", "Lincoln", "Wilkes"],
    "fulton-county": ["Fulton"],
}

REGION_LABELS = {
    "greater-athens-area": "Greater Athens Area",
    "greater-savannah-area": "Greater Savannah Area",
    "gwinnett-county": "Gwinnett County",
    "metro-atlanta-north": "Metro Atlanta North",
    "dekalb-county": "Dekalb County",
    "metro-atlanta-south": "Metro Atlanta South",
    "macon": "Macon",
    "fall-line-sandhills": "Fall Line Sandhills",
    "west-piedmont": "West Piedmont",
    "north-georgia-mountains": "North Georgia Mountains",
    "inland-coastal-plain": "Inland Coastal Plain",
    "broad-river-watershed": "Broad River Watershed",
    "columbus-area": "Columbus Area",
    "golden-isles": "Golden Isles",
    "greater-augusta-area": "Greater Augusta Area",
    "fulton-county": "Fulton County",
}

REGION_GROUPS = {
    "Metro Atlanta": ["metro-atlanta-north", "metro-atlanta-south", "fulton-county", "dekalb-county", "gwinnett-county"],
    "Southeast Georgia": ["golden-isles"],
    "Savannah Area": ["greater-savannah-area"],
    "Athens Area": ["greater-athens-area"],
    "Augusta Area": ["greater-augusta-area"],
    "Central Georgia": ["macon", "fall-line-sandhills"],
    "West Georgia": ["west-piedmont", "columbus-area"],
    "North Georgia": ["north-georgia-mountains", "broad-river-watershed"],
    "South Georgia": ["inland-coastal-plain"],
}

COLORS = {
    "greater-athens-area": "#b8323c", "greater-savannah-area": "#2878a0", "gwinnett-county": "#b39b00",
    "metro-atlanta-north": "#4f8f3a", "dekalb-county": "#707070", "metro-atlanta-south": "#8c4824",
    "macon": "#08786e", "fall-line-sandhills": "#c45b00", "west-piedmont": "#17605c",
    "north-georgia-mountains": "#4e9b8d", "inland-coastal-plain": "#82609f",
    "broad-river-watershed": "#365f9e", "columbus-area": "#ad4f8c", "golden-isles": "#b8860b",
    "greater-augusta-area": "#79518d", "fulton-county": "#bd7745",
}

GROUP_COLORS = {
    "Metro Atlanta": "#ba4c00", "Southeast Georgia": "#137b5e", "Savannah Area": "#5d55a8",
    "Athens Area": "#c81d78", "Augusta Area": "#548c17", "Central Georgia": "#b38300",
    "West Georgia": "#8b5b1a", "North Georgia": "#176c99", "South Georgia": "#69934a",
}


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


def panel(features: list[dict], categories: dict[str, list[str]], colors: dict[str, str],
          title: str, y0: int, labels: dict[str, str] | None = None) -> tuple[str, int]:
    """Return an SVG group (map + legend) placed at y0 and its height."""
    regions = categories
    county_region = {c.lower(): r for r, cs in regions.items() for c in cs}

    names = {f["properties"]["NAME"].lower() for f in features}
    if names != set(county_region):
        raise SystemExit(f"County mismatch: {sorted(names ^ set(county_region))}")
    missing = [r for r in regions if r not in colors]
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
        label = (labels or {}).get(region, region)
        paths.append(
            f'<path d="{d}" fill="{colors[region]}"><title>{escape(name)} - {escape(label)}</title></path>'
        )

    region_lats: dict[str, list[float]] = {}
    for f in features:
        ys = [p[1] for r in rings(f["geometry"]) for p in r]
        region_lats.setdefault(county_region[f["properties"]["NAME"].lower()], []).append(
            (min(ys) + max(ys)) / 2
        )
    north_to_south = sorted(
        (r for r in regions if r in region_lats), key=lambda r: -sum(region_lats[r]) / len(region_lats[r])
    ) + [r for r in regions if r not in region_lats]

    legend = [
        f'<rect x="{PAD + MAP_WIDTH + 20}" y="{PAD + i * 22}" width="14" height="14" fill="{colors[r]}" '
        f'stroke="#fff" stroke-width="0.5"/>'
        f'<text x="{PAD + MAP_WIDTH + 42}" y="{PAD + 12 + i * 22}">'
        f'{escape(r)}</text>'
        for i, r in enumerate(north_to_south)
    ]
    panel_height = max(height, 2 * PAD + len(legend) * 22)
    svg = (
        f'<g transform="translate(0,{y0})">\n'
        f'<text x="{PAD}" y="26" font-size="18" font-weight="bold">{escape(title)}</text>\n'
        f'<g stroke="#fff" stroke-width="0.6" stroke-linejoin="round">\n' + "\n".join(paths) + "\n</g>\n"
        + "\n".join(legend)
        + "\n</g>\n"
    )
    return svg, panel_height


def main(out: Path):
    regions = REGIONS
    groups = {g: [c for r in rs for c in regions[r]] for g, rs in REGION_GROUPS.items()}
    features = load_counties()

    top, top_height = panel(features, groups, GROUP_COLORS, "Categories", 0)
    bottom, bottom_height = panel(features, regions, COLORS, "Regions", top_height, REGION_LABELS)
    width = PAD + MAP_WIDTH + LEGEND_WIDTH
    total = top_height + bottom_height
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total}" '
        f'width="{width}" font-family="sans-serif" font-size="13" fill="#fff">\n'
        f'<rect width="100%" height="100%" fill="#000"/>\n' + top + bottom + "</svg>\n",
        encoding="utf-8",
    )
    print(f"Wrote {out} ({len(features)} counties, {len(groups)} categories, {len(regions)} regions)")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "georgia_regions.svg"))
