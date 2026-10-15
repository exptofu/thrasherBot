"""Render georgia_regions.svg: proposed categories (top) and regions (bottom) defined below.

The proposal is a preview only; bot.py REGIONS/REGION_GROUPS are not read or changed.

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

# Proposed regions: 20 total.
REGIONS = {
    "dekalb": ["DeKalb"],
    "fulton": ["Fulton"],
    "cobb": ["Cobb"],
    "gwinnett": ["Gwinnett"],
    "cherokee": ["Cherokee"],
    "glynn": ["Glynn"],
    "columbus-fall-line": ["Muscogee", "Harris", "Chattahoochee", "Marion", "Talbot", "Taylor"],
    "athens-metro": ["Clarke", "Oconee", "Oglethorpe"],
    "augusta-metro": ["Richmond", "Columbia"],
    "macon-expanded": [
        "Bibb", "Houston", "Jones", "Peach", "Crawford", "Twiggs", "Wilkinson", "Monroe",
        "Baldwin", "Macon",
    ],
    "chatham-effingham": ["Chatham", "Effingham"],
    "colonial-coast": ["McIntosh", "Camden", "Bryan", "Liberty"],
    "north-georgia": [
        "Rabun", "Habersham", "Lumpkin", "Fannin", "Union", "Towns", "White", "Dawson",
        "Gilmer", "Pickens", "Floyd", "Bartow", "Whitfield", "Catoosa", "Gordon", "Chattooga",
        "Dade", "Walker", "Polk", "Murray",
    ],
    "upper-piedmont": [
        "Hall", "Forsyth", "Barrow", "Jackson", "Madison", "Franklin", "Banks", "Hart",
        "Elbert", "Stephens",
    ],
    "west-central": ["Coweta", "Carroll", "Paulding", "Haralson", "Douglas", "Heard", "Troup", "Meriwether"],
    "south-atlanta": [
        "Clayton", "Fayette", "Henry", "Rockdale", "Newton", "Walton", "Morgan", "Greene",
        "Putnam", "Jasper", "Spalding", "Butts", "Lamar", "Pike", "Upson",
    ],
    "early-wiregrass": [
        "Early", "Decatur", "Thomas", "Sumter", "Dougherty", "Lee", "Worth", "Terrell",
        "Schley", "Webster", "Stewart", "Quitman", "Randolph", "Clay", "Calhoun", "Seminole",
        "Miller", "Baker", "Grady", "Mitchell", "Crisp", "Dooly", "Wilcox", "Turner", "Tift",
        "Brooks", "Cook", "Lowndes", "Berrien", "Colquitt", "Lanier",
    ],
    "west-sandhills": [
        "Laurens", "Washington", "Hancock", "Warren", "Taliaferro", "Glascock", "Jefferson",
        "Johnson", "Emanuel", "Bleckley", "Dodge", "Pulaski", "Telfair", "Wheeler", "Ben Hill",
        "Irwin",
    ],
    "east-sandhills": [
        "Charlton", "Bulloch", "Ware", "Pierce", "Brantley", "Clinch", "Atkinson", "Coffee",
        "Jeff Davis", "Appling", "Bacon", "Treutlen", "Montgomery", "Toombs", "Candler",
        "Jenkins", "Screven", "Tattnall", "Evans", "Long", "Wayne", "Echols",
    ],
    "upper-savannah": ["Burke", "McDuffie", "Lincoln", "Wilkes"],
}

REGION_LABELS = {
    "dekalb": "DeKalb County",
    "fulton": "Fulton County",
    "cobb": "Cobb County",
    "gwinnett": "Gwinnett County",
    "cherokee": "Cherokee County",
    "glynn": "Glynn County",
    "columbus-fall-line": "Columbus-Fall Line",
    "athens-metro": "Athens Area",
    "augusta-metro": "Augusta Area",
    "macon-expanded": "Macon Area",
    "chatham-effingham": "Chatham-Effingham Coast",
    "colonial-coast": "Mid-Coast Georgia",
    "north-georgia": "North Georgia Mountains",
    "upper-piedmont": "Upper Piedmont Lakes",
    "west-central": "West Central Piedmont",
    "south-atlanta": "South Atlanta Piedmont",
    "early-wiregrass": "Southwest Georgia",
    "west-sandhills": "West Sandhills & Fall Line",
    "east-sandhills": "East Sandhills",
    "upper-savannah": "Upper Savannah",
}

REGION_GROUPS = {
    "Metro Atlanta": ["dekalb", "fulton", "cobb", "gwinnett", "cherokee"],
    "North Georgia": ["north-georgia"],
    "Northeast Georgia": ["upper-piedmont", "athens-metro"],
    "West Georgia": ["columbus-fall-line", "west-central"],
    "Central Georgia": ["macon-expanded", "south-atlanta", "west-sandhills"],
    "East Georgia": ["augusta-metro", "east-sandhills", "upper-savannah"],
    "Southwest Georgia": ["early-wiregrass"],
    "Coastal Georgia": ["glynn", "chatham-effingham", "colonial-coast"],
}

COLORS = {
    "dekalb": "#fffac8", "fulton": "#aaffc3", "cobb": "#ffe119", "gwinnett": "#3cb44b",
    "cherokee": "#4363d8", "glynn": "#00ff00", "columbus-fall-line": "#f032e6",
    "athens-metro": "#fabed4", "augusta-metro": "#f58231", "macon-expanded": "#bfef45",
    "chatham-effingham": "#a9a9a9", "colonial-coast": "#00ffff", "north-georgia": "#42d4f4",
    "upper-piedmont": "#e6194B", "west-central": "#469990", "south-atlanta": "#660033",
    "early-wiregrass": "#9A6324", "west-sandhills": "#000075", "east-sandhills": "#911eb4",
    "upper-savannah": "#e6beff",
}

GROUP_COLORS = {
    "Metro Atlanta": "#d95f02",
    "North Georgia": "#1b9e77",
    "Northeast Georgia": "#7570b3",
    "West Georgia": "#e7298a",
    "Central Georgia": "#66a61e",
    "East Georgia": "#e6ab02",
    "Southwest Georgia": "#a6761d",
    "Coastal Georgia": "#1f78b4",
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
