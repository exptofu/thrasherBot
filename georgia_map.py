"""Render georgia_regions.svg from the region/category layout used by the bot.

Stdlib only. County outlines come from the public plotly/datasets GeoJSON (Census data).
Usage: python georgia_map.py
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

# Keep these county assignments and categories synchronized with bot.py.
REGIONS = {
    "greater-athens": ["Barrow", "Walton", "Greene", "Morgan", "Oglethorpe", "Jackson", "Madison"],
    "athens": ["Clarke","Oconee"],
    "greater-savannah": ["Chatham", "Bryan", "Liberty", "Effingham"],
    "gwinnett-county": ["Gwinnett"],
    "metro-atlanta-north": ["Cobb", "Forsyth", "Douglas", "Cherokee", "Hall", "Bartow", "Paulding"],
    "dekalb-county": ["DeKalb"],
    "metro-atlanta-south": ["Coweta", "Henry", "Rockdale", "Newton", "Clayton", "Fayette", "Spalding", "Butts"],
    "greater-macon": [
        "Bibb", "Jones", "Twiggs", "Houston", "Peach", "Crawford", "Monroe",
    ],
    "fall-line-sandhills": [
        "Pike", "Upson", "Lamar", "Wilkinson", "Baldwin", "Jasper", "Putnam", "Hancock", "Washington", "Pulaski",
        "Bleckley", "Laurens", "Johnson", "Taylor", "Macon", "Dooly", "Schley", "Dodge", "Treutlen",
    ],
    "west-piedmont": ["Carroll", "Heard", "Haralson", "Polk"],
    "north-georgia-mountains": [
        "Gilmer", "Pickens", "Dawson", "Union", "Fannin", "Lumpkin", "White", "Towns", "Rabun", "Habersham",
    ],
    "okefenokee-basin": [
        "Atkinson", "Ware", "Bacon", "Pierce", "Brantley", "Clinch", "Charlton",
    ],
    "greater-valdosta": [
        "Colquitt", "Cook", "Brooks", "Lowndes", "Berrien", "Lanier", "Echols",
    ],
    "lake-seminole-watershed": [
        "Sumter", "Crisp", "Randolph", "Terrell", "Lee", "Worth", "Turner", "Clay", "Calhoun",
        "Dougherty", "Tift", "Early", "Miller", "Baker", "Mitchell", "Seminole", "Decatur", "Grady", "Thomas",
    ],
    "three-rivers-basin": [
        "Wilcox", "Telfair", "Ben Hill", "Irwin", "Coffee", "Jeff Davis", "Wheeler", "Montgomery",
        "Toombs", "Appling", "Tattnall", "Long", "Wayne",
    ],
    "broad-river-watershed": ["Elbert", "Hart", "Stephens", "Franklin", "Banks"],
    "greater-columbus": ["Talbot", "Marion", "Stewart", "Webster", "Quitman", "Harris", "Muscogee", "Chattahoochee","Troup", "Meriwether"],
    "golden-isles": ["McIntosh", "Glynn", "Camden"],
    "greater-augusta": ["Taliaferro", "Warren", "Glascock", "Jenkins", "Burke", "Jefferson", "McDuffie", "Lincoln", "Wilkes"],
    "augusta": ["Richmond", "Columbia",],
    "fulton-county": ["Fulton"],
    "ridge-and-valleys": ["Floyd", "Chattooga", "Walker", "Dade", "Catoosa", "Whitfield", "Gordon", "Murray"],
    "greater-statesboro": ["Emanuel", "Evans", "Candler", "Bulloch", "Screven"],
}

REGION_LABELS = {
    "greater-athens": "Greater Athens",
    "athens": "Athens",
    "greater-savannah": "Greater Savannah",
    "gwinnett-county": "Gwinnett",
    "metro-atlanta-north": "Metro Atlanta North",
    "dekalb-county": "Dekalb",
    "metro-atlanta-south": "Metro Atlanta South",
    "greater-macon": "Greater Macon",
    "fall-line-sandhills": "Fall Line Sandhills",
    "west-piedmont": "West Piedmont",
    "north-georgia-mountains": "North Georgia Mountains",
    "okefenokee-basin": "Okefenokee Basin",
    "greater-valdosta": "Greater Valdosta",
    "lake-seminole-watershed": "Lake Seminole Watershed",
    "three-rivers-basin": "Three Rivers Basin",
    "broad-river-watershed": "Broad River Watershed",
    "greater-columbus": "Greater Columbus",
    "golden-isles": "Golden Isles",
    "greater-augusta": "Greater Augusta",
    "augusta": "Augusta",
    "fulton-county": "Fulton",
    "ridge-and-valleys": "Ridge and Valleys",
    "greater-statesboro": "Greater Statesboro",
}

def validate_unique_counties() -> dict[str, str]:
    assigned: dict[str, str] = {}
    for region_name, counties in REGIONS.items():
        for county in counties:
            key = county.lower()
            if key in assigned:
                raise ValueError(f"County '{county}' is assigned to multiple regions: {assigned[key]} and {region_name}")
            assigned[key] = region_name
    return assigned


COUNTY_REGION = validate_unique_counties()

REGION_GROUPS = {
    "Metro Atlanta": ["metro-atlanta-south", "metro-atlanta-north", "fulton-county", "dekalb-county", "gwinnett-county"],
    "Southeast Georgia": ["golden-isles"],
    "Savannah Area": ["greater-savannah"],
    "Athens Area": ["greater-athens", "athens",],
    "Augusta Area": ["greater-augusta", "augusta",],
    "Central Georgia": ["fall-line-sandhills", "greater-macon",],
    "West Georgia": ["west-piedmont", "greater-columbus"],
    "Statesboro Area": ["greater-statesboro"],
    "North Georgia": ["broad-river-watershed", "north-georgia-mountains", "ridge-and-valleys"],
    "South Georgia": ["okefenokee-basin", "lake-seminole-watershed", "three-rivers-basin", "greater-valdosta"],
}

GROUP_COLORS = {
    "North Georgia": "#1a6aa3", 
    "Metro Atlanta": "#ba5e74", 
    "Athens Area": "#2da172", 
    "Augusta Area": "#ba845e", 
    "West Georgia": "#b63ec7", 
    "Central Georgia": "#4f4ea3",
    "Statesboro Area": "#2b7a8a",
    "Savannah Area": "#b6323d",
    "South Georgia": "#4d7f2d",
    "Southeast Georgia": "#EFBF04",
}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in range(0, len(value), 2))


def rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    r /= 255
    g /= 255
    b /= 255
    max_channel = max(r, g, b)
    min_channel = min(r, g, b)
    delta = max_channel - min_channel
    lightness = (max_channel + min_channel) / 2

    if delta == 0:
        hue = 0.0
        saturation = 0.0
    else:
        saturation = delta / (1 - abs(2 * lightness - 1))
        if max_channel == r:
            hue = ((g - b) / delta) % 6
        elif max_channel == g:
            hue = (b - r) / delta + 2
        else:
            hue = (r - g) / delta + 4
        hue *= 60
    return hue, saturation, lightness


def hsl_to_hex(h: float, s: float, l: float) -> str:
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if 0 <= h < 60:
        r, g, b = c, x, 0
    elif 60 <= h < 120:
        r, g, b = x, c, 0
    elif 120 <= h < 180:
        r, g, b = 0, c, x
    elif 180 <= h < 240:
        r, g, b = 0, x, c
    elif 240 <= h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return "#" + "".join(f"{max(0, min(255, round(v * 255 + m * 255))):02x}" for v in (r, g, b))


def build_region_colors(region_groups: dict[str, list[str]], group_colors: dict[str, str]) -> dict[str, str]:
    region_colors: dict[str, str] = {}
    for category, regions in region_groups.items():
        base_color = group_colors[category]
        h, s, l = rgb_to_hsl(*hex_to_rgb(base_color))
        total = max(len(regions) - 1, 1)
        for index, region in enumerate(regions):
            position = index / total
            sat = max(0.30, min(0.95, s * (0.75 + position * 0.85)))
            if index % 2 == 0:
                light = max(0.18, min(0.80, l + 0.10 - position * 0.16))
            else:
                light = max(0.18, min(0.80, l - 0.10 + position * 0.16))
            if len(regions) > 2:
                sat = max(0.28, min(0.97, sat + ((index % 3) - 1) * 0.12))
                light = max(0.16, min(0.82, light + ((index % 2) * 0.18 - 0.09)))
            region_colors[region] = hsl_to_hex(h, sat, light)
    return region_colors


COLORS = build_region_colors(REGION_GROUPS, GROUP_COLORS)
# COLORS["greater-macon"] = "#ad8700"
# COLORS["fall-line-sandhills"] = "#d9a900"

# Small offsets keep labels readable in the most crowded parts of the map.
LABEL_OFFSETS = {"fulton-county": (-10, 14), "fall-line-sandhills": (45, 40), 
                "metro-atlanta-north":(0,-20),"west-piedmont":(0,20),"greater-augusta":(30,30),"greater-athens":(0,30)}


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


def normalize_segment(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    left, right = sorted(((round(p1[0], 2), round(p1[1], 2)), (round(p2[0], 2), round(p2[1], 2))))
    return left, right


def panel(features: list[dict], categories: dict[str, list[str]], colors: dict[str, str],
          title: str, y0: int, labels: dict[str, str] | None = None) -> tuple[str, int]:
    """Return an SVG group for the map placed at y0 and its height."""
    regions = categories
    if title == "Categories":
        region_to_group = {region: group for group, region_names in REGION_GROUPS.items() for region in region_names}
        county_region = {
            county.lower(): region_to_group[COUNTY_REGION[county.lower()]]
            for county in COUNTY_REGION
        }
    else:
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
    centroids = {region: [0.0, 0.0, 0.0] for region in regions}
    county_segments: dict[str, set[tuple[tuple[float, float], tuple[float, float]]]] = {}
    county_group = {}
    if title == "Regions":
        region_to_group = {region: group for group, region_names in REGION_GROUPS.items() for region in region_names}
        county_group = {county.lower(): region_to_group[COUNTY_REGION[county.lower()]] for county in COUNTY_REGION}

    for f in sorted(features, key=lambda f: f["properties"]["NAME"]):
        name = f["properties"]["NAME"]
        region = county_region[name.lower()]
        projected = [[project(p) for p in r] for r in rings(f["geometry"])]
        county_segments[name.lower()] = set()
        for ring in projected:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                cross = x1 * y2 - x2 * y1
                centroids[region][0] += cross
                centroids[region][1] += (x1 + x2) * cross
                centroids[region][2] += (y1 + y2) * cross
                county_segments[name.lower()].add(normalize_segment((x1, y1), (x2, y2)))
        d = " ".join(
            "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in r) + "Z" for r in projected
        )
        label = (labels or {}).get(region, region)
        if title == "Categories":
            stroke_color = "#fff"
            stroke_width = "2.5"
        elif title == "Regions":
            stroke_color = "#f2f2f2"
            stroke_width = "0.8"
        else:
            stroke_color = "#fff"
            stroke_width = "0.6"
        paths.append(
            f'<path d="{d}" fill="{colors[region]}" stroke="{stroke_color}" stroke-width="{stroke_width}" stroke-linejoin="round"><title>{escape(name)} - {escape(label)}</title></path>'
        )

    if title == "Regions":
        segment_map: dict[tuple[tuple[float, float], tuple[float, float]], set[str]] = {}
        for county_name, segments in county_segments.items():
            for segment in segments:
                segment_map.setdefault(segment, set()).add(county_name)

        state_boundary_segments: list[tuple[float, float, float, float]] = []
        category_boundary_segments: list[tuple[float, float, float, float]] = []
        seen: set[tuple[tuple[float, float], tuple[float, float]]] = set()
        for segment, counties in segment_map.items():
            if len(counties) == 1:
                (x1, y1), (x2, y2) = segment
                state_boundary_segments.append((x1, y1, x2, y2))
                continue
            groups = {county_group.get(county, "") for county in counties if county in county_group}
            if len(groups) <= 1:
                continue
            if segment in seen:
                continue
            seen.add(segment)
            (x1, y1), (x2, y2) = segment
            category_boundary_segments.append((x1, y1, x2, y2))

        if state_boundary_segments:
            state_d = " ".join(
                f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"
                for x1, y1, x2, y2 in state_boundary_segments
            )
            paths.append(
                f'<path d="{state_d}" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="butt" stroke-linejoin="miter" opacity="0.95"/>'
            )

        if category_boundary_segments:
            boundary_d = " ".join(
                f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"
                for x1, y1, x2, y2 in category_boundary_segments
            )
            paths.append(
                f'<path d="{boundary_d}" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="butt" stroke-linejoin="miter" opacity="0.9"/>'
            )

    map_labels = []
    for region, (area2, x_moment, y_moment) in centroids.items():
        if not area2:
            continue
        label = (labels or {}).get(region, region)
        font_size = 12 if title == "Categories" else 12
        offset_key = region.lower().replace(" ", "-")
        offset_x, offset_y = LABEL_OFFSETS.get(offset_key, (0, 0))
        map_labels.append(
            f'<text x="{x_moment / (3 * area2) + offset_x:.1f}" '
            f'y="{y_moment / (3 * area2) + offset_y:.1f}" '
            f'text-anchor="middle" dominant-baseline="central" font-size="{font_size}" '
            f'font-weight="bold" fill="#fff" stroke="#000" stroke-width="4" '
            f'stroke-linejoin="round" paint-order="stroke">{escape(label)}</text>'
        )

    legend = ""
    if title == "Regions":
        legend_items = []
        legend_x = MAP_WIDTH - 100
        legend_y = 52
        for index, (category, color) in enumerate(GROUP_COLORS.items()):
            item_y = legend_y + index * 22
            legend_items.append(
                f'<rect x="{legend_x}" y="{item_y}" width="18" height="18" fill="{color}" stroke="#fff" stroke-width="1"/>'
            )
            legend_items.append(
                f'<text x="{legend_x + 24}" y="{item_y + 13}" font-size="12" fill="#fff">{escape(category)}</text>'
            )
        legend = "\n".join(legend_items)

    panel_height = height
    svg = (
        f'<g transform="translate(0,{y0})">\n'
        f'<text x="{PAD}" y="26" font-size="18" font-weight="bold">{escape(title)}</text>\n'
        f'<g>\n' + "\n".join(paths) + "\n</g>\n"
        + "\n".join(map_labels) + "\n"
        + legend
        + "\n</g>\n"
    )
    return svg, panel_height


def main():
    regions = REGIONS
    groups = {g: [c for r in rs for c in regions[r]] for g, rs in REGION_GROUPS.items()}
    features = load_counties()

    output_dir = Path(__file__).parent
    for filename, categories, colors, title, labels in (
        ("georgia_regions.svg", regions, COLORS, "Regions", REGION_LABELS),
    ):
        svg, height = panel(features, categories, colors, title, 0, labels)
        width = MAP_WIDTH + 2 * PAD
        out = output_dir / filename
        out.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" font-family="sans-serif" font-size="13" fill="#fff">\n'
            f'<rect width="100%" height="100%" fill="#000"/>\n' + svg + "</svg>\n",
            encoding="utf-8",
        )
        print(f"Wrote {out} ({len(features)} counties, {len(categories)} {title.lower()})")


if __name__ == "__main__":
    main()
