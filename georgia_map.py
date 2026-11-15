"""Render georgia_regions.svg from the region/category layout used by the bot.

Stdlib only. County outlines come from the public plotly/datasets GeoJSON (Census data).
Usage: python georgia_map.py
"""
import json
import math
import re
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
GEORGIA_FIPS = "13"
SOUTH_CAROLINA_FIPS = "45"  # For Aiken and Edgefield counties
ALABAMA_FIPS = "01"  # For Russell County
MAP_WIDTH = 620
PAD = 40

# Keep these county assignments and categories synchronized with bot.py.
REGIONS = {
    "greater-athens": ["Barrow", "Walton", "Greene", "Morgan", "Oglethorpe", "Jackson", "Madison", "Clarke", "Oconee"],
    "greater-savannah": ["Chatham", "Bryan", "Liberty", "Effingham"],
    "gwinnett-county": ["Gwinnett"],
    "cobb-county": ["Cobb"],
    "metro-atlanta-north": ["Forsyth", "Douglas", "Cherokee", "Hall", "Bartow", "Paulding"],
    "dekalb-county": ["DeKalb"],
    "metro-atlanta-south": ["Coweta", "Henry", "Rockdale", "Newton", "Clayton", "Fayette", "Spalding", "Butts"],
    "greater-macon": [
        "Bibb", "Jones", "Twiggs", "Houston", "Peach", "Crawford", "Monroe",
    ],
    "fall-line-sandhills": [
        "Pike", "Upson", "Lamar", "Wilkinson", "Baldwin", "Jasper", "Putnam", "Hancock", "Washington", "Pulaski",
        "Bleckley", "Laurens", "Johnson", "Taylor", "Macon", "Dooly", "Schley", "Dodge", "Treutlen",
    ],
    "west-piedmont": ["Carroll", "Heard", "Haralson"],
    "blue-ridge": [
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
    "greater-columbus": ["Talbot", "Marion", "Stewart", "Webster", "Quitman", "Harris", "Muscogee", "Chattahoochee","Troup", "Meriwether", "Russell"],
    "golden-isles": ["McIntosh", "Glynn", "Camden"],
    "greater-augusta": ["Taliaferro", "Warren", "Glascock", "Jenkins", "Burke", "Jefferson", "McDuffie", "Lincoln", "Wilkes", "Richmond", "Columbia", "Aiken", "Edgefield"],
    "fulton-county": ["Fulton"],
    "ridge-and-valleys": ["Floyd", "Chattooga", "Walker", "Dade", "Catoosa", "Whitfield", "Gordon", "Murray", "Polk"],
    "greater-statesboro": ["Emanuel", "Evans", "Candler", "Bulloch", "Screven"],
}

REGION_LABELS = {
    "greater-athens": "Greater Athens",
    "greater-savannah": "Greater Savannah",
    "gwinnett-county": "Gwinnett",
    "metro-atlanta-north": "Metro Atlanta North",
    "dekalb-county": "Dekalb",
    "cobb-county": "Cobb",
    "metro-atlanta-south": "Metro Atlanta South",
    "greater-macon": "Greater Macon",
    "fall-line-sandhills": "Fall Line Sandhills",
    "west-piedmont": "West Piedmont",
    "blue-ridge": "Blue Ridge",
    "okefenokee-basin": "Okefenokee Basin",
    "greater-valdosta": "Greater Valdosta",
    "lake-seminole-watershed": "Lake Seminole Watershed",
    "three-rivers-basin": "Three Rivers Basin",
    "broad-river-watershed": "Broad River Watershed",
    "greater-columbus": "Greater Columbus",
    "golden-isles": "Golden Isles",
    "greater-augusta": "Greater Augusta",
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
    "Metro Atlanta": ["metro-atlanta-south", "metro-atlanta-north", "fulton-county", "dekalb-county", "gwinnett-county","cobb-county"],
    "Southeast Georgia": ["golden-isles"],
    "Savannah Area": ["greater-savannah"],
    "Athens Area": ["greater-athens"],
    "Augusta Area": ["greater-augusta"],
    "Central Georgia": ["fall-line-sandhills", "greater-macon",],
    "West Georgia": ["west-piedmont", "greater-columbus"],
    "North Georgia": ["broad-river-watershed", "blue-ridge", "ridge-and-valleys"],
    "South Georgia": ["okefenokee-basin", "lake-seminole-watershed", "three-rivers-basin", "greater-valdosta"],
    "Statesboro Area": ["greater-statesboro"],
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
                "metro-atlanta-north":(0,-20),"west-piedmont":(0,0),"greater-augusta":(0,0)}


def load_counties() -> list[dict]:
    cache = Path(__file__).parent / ".cache" / "geojson-counties-fips.json"
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(GEOJSON_URL, cache)
    data = json.loads(cache.read_text(encoding="utf-8"))
    sc_counties_needed = {"aiken", "edgefield"}
    al_counties_needed = {"russell"}
    return [
        f for f in data["features"] 
        if f["properties"]["STATE"] == GEORGIA_FIPS 
        or (f["properties"]["STATE"] == SOUTH_CAROLINA_FIPS and f["properties"]["NAME"].lower() in sc_counties_needed)
        or (f["properties"]["STATE"] == ALABAMA_FIPS and f["properties"]["NAME"].lower() in al_counties_needed)
    ]


def rings(geometry: dict):
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for poly in polys:
        yield from poly


def normalize_segment(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    left, right = sorted(((round(p1[0], 1), round(p1[1], 1)), (round(p2[0], 1), round(p2[1], 1))))
    return left, right


def segments_to_path_d(segments: list[tuple[float, float, float, float]]) -> str:
    """Stitch unordered (x1, y1, x2, y2) segments into continuous SVG polylines."""
    if not segments:
        return ""

    # Build adjacency graph using rounded coordinate tuples as keys
    adj: dict[tuple[float, float], list[tuple[float, float]]] = {}
    edge_counts: dict[tuple[tuple[float, float], tuple[float, float]], int] = {}

    for x1, y1, x2, y2 in segments:
        p1 = (round(x1, 1), round(y1, 1))
        p2 = (round(x2, 1), round(y2, 1))
        if p1 == p2:
            continue
        adj.setdefault(p1, []).append(p2)
        adj.setdefault(p2, []).append(p1)
        edge = (p1, p2) if p1 < p2 else (p2, p1)
        edge_counts[edge] = edge_counts.get(edge, 0) + 1

    def take_edge(u: tuple[float, float], v: tuple[float, float]) -> bool:
        edge = (u, v) if u < v else (v, u)
        if edge_counts.get(edge, 0) > 0:
            edge_counts[edge] -= 1
            return True
        return False

    polylines: list[list[tuple[float, float]]] = []

    # 1. Start chains from junction/endpoint nodes (degree != 2)
    for node, neighbors in adj.items():
        if len(neighbors) != 2:
            for nxt in neighbors:
                if take_edge(node, nxt):
                    chain = [node, nxt]
                    curr = nxt
                    while len(adj.get(curr, [])) == 2:
                        n1, n2 = adj[curr]
                        candidate = n1 if take_edge(curr, n1) else (n2 if take_edge(curr, n2) else None)
                        if candidate is None:
                            break
                        chain.append(candidate)
                        curr = candidate
                    polylines.append(chain)

    # 2. Catch any remaining closed loops (all nodes degree == 2)
    for node, neighbors in adj.items():
        for nxt in neighbors:
            if take_edge(node, nxt):
                chain = [node, nxt]
                curr = nxt
                while True:
                    moved = False
                    for candidate in adj.get(curr, []):
                        if take_edge(curr, candidate):
                            chain.append(candidate)
                            curr = candidate
                            moved = True
                            break
                    if not moved:
                        break
                polylines.append(chain)

    # Format chains as SVG path commands (use Z if closed loop)
    d_parts = []
    for chain in polylines:
        is_closed = len(chain) > 2 and chain[0] == chain[-1]
        pts = chain[:-1] if is_closed else chain
        cmd = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        if is_closed:
            cmd += " Z"
        d_parts.append(cmd)

    return " ".join(d_parts)


def panel(features: list[dict], categories: dict[str, list[str]], colors: dict[str, str],
          title: str, y0: int, labels: dict[str, str] | None = None) -> tuple[str, int]:
    """Return an SVG group for the map placed at y0 and its height."""
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
    centroids = {region: [0.0, 0.0, 0.0] for region in regions}
    county_segments: dict[str, set[tuple[tuple[float, float], tuple[float, float]]]] = {}
    sc_counties = {"aiken", "edgefield"}
    al_counties = {"russell"}
    
    # Count counties per region for detecting multi-county regions
    region_county_count = {}
    for county_name, region in county_region.items():
        region_county_count[region] = region_county_count.get(region, 0) + 1
    
    # Track region-to-region segments for lower opacity
    # Using a list of regions for each segment to detect same-region internal borders
    region_segment_map_list = {}

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
                segment = normalize_segment((x1, y1), (x2, y2))
                county_segments[name.lower()].add(segment)
                # Track segments by region (use list to detect same-region internal borders)
                if segment not in region_segment_map_list:
                    region_segment_map_list[segment] = []
                region_segment_map_list[segment].append(region)
        d = " ".join(
            "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in r) + "Z" for r in projected
        )
        
        # Use pattern fill for out-of-state counties, solid color for Georgia
        fill_color = colors[region]
        if name.lower() in sc_counties:
            # For SC counties: base color + black striped pattern overlay
            paths.append(
                f'<path d="{d}" fill="{fill_color}" stroke="#f2f2f2" stroke-width="0.8" stroke-linejoin="round"><title>{escape(name)}</title></path>'
            )
            # Striped overlay with inset to avoid border overlap
            paths.append(
                f'<path d="{d}" fill="url(#oos-stripes)" stroke="none" opacity="0.85"><title>{escape(name)} (South Carolina)</title></path>'
            )
        elif name.lower() in al_counties:
            # For AL counties: base color + black striped pattern overlay
            paths.append(
                f'<path d="{d}" fill="{fill_color}" stroke="#f2f2f2" stroke-width="0.8" stroke-linejoin="round"><title>{escape(name)}</title></path>'
            )
            # Striped overlay with inset to avoid border overlap
            paths.append(
                f'<path d="{d}" fill="url(#oos-stripes)" stroke="none" opacity="0.85"><title>{escape(name)} (Alabama)</title></path>'
            )
        else:
            paths.append(
                f'<path d="{d}" fill="{fill_color}" stroke="none"><title>{escape(name)}</title></path>'
            )

    # Build segment map to determine which borders should be drawn and with what opacity
    segment_map: dict[tuple[tuple[float, float], tuple[float, float]], set[str]] = {}
    for county_name, segments in county_segments.items():
        for segment in segments:
            segment_map.setdefault(segment, set()).add(county_name)

    # Categorize segments into different types
    state_boundary_segments: list[tuple[float, float, float, float]] = []
    ga_to_oos_segments: list[tuple[float, float, float, float]] = []
    region_boundary_segments: list[tuple[float, float, float, float]] = []
    internal_region_segments: list[tuple[float, float, float, float]] = []
    
    oos_counties = sc_counties | al_counties
    
    for segment, counties in segment_map.items():
        (x1, y1), (x2, y2) = segment
        
        if len(counties) == 1:
            # External boundary (state edge)
            county_name = list(counties)[0]
            if county_name not in oos_counties:
                state_boundary_segments.append((x1, y1, x2, y2))
        elif len(counties) == 2:
            county1, county2 = list(counties)
            region1 = county_region[county1]
            region2 = county_region[county2]
            is_oos_1 = county1 in oos_counties
            is_oos_2 = county2 in oos_counties
            
            # Check if border is between GA and out-of-state
            if is_oos_1 != is_oos_2:
                ga_to_oos_segments.append((x1, y1, x2, y2))
            # Check if it's an internal region border
            elif region1 == region2 and region_county_count.get(region1, 1) > 1:
                internal_region_segments.append((x1, y1, x2, y2))
            # Otherwise it's a border between different regions
            else:
                region_boundary_segments.append((x1, y1, x2, y2))

    # 1. Internal county borders (thin, subtle, butt caps so tripoints stay clean)
    if internal_region_segments:
        internal_d = segments_to_path_d(internal_region_segments)
        paths.append(
            f'<path d="{internal_d}" fill="none" stroke="#f2f2f2" stroke-width="0.8" '
            f'stroke-linecap="butt" stroke-linejoin="round" opacity="0.5"/>'
        )

    # 2. Region borders (continuous polylines with round joins and butt caps)
    if region_boundary_segments:
        region_d = segments_to_path_d(region_boundary_segments)
        paths.append(
            f'<path d="{region_d}" fill="none" stroke="#f2f2f2" stroke-width="1.2" '
            f'stroke-linecap="butt" stroke-linejoin="round"/>'
        )

    # 3. Thick outer state & GA-to-OOS borders combined into one continuous path
    all_state_segments = state_boundary_segments + ga_to_oos_segments
    if all_state_segments:
        state_d = segments_to_path_d(all_state_segments)
        paths.append(
            f'<path d="{state_d}" fill="none" stroke="#fff" stroke-width="3.2" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="0.95"/>'
        )

    map_labels = []
    for region, (area2, x_moment, y_moment) in centroids.items():
        if not area2:
            continue
        label = (labels or {}).get(region, region)
        offset_key = region.lower().replace(" ", "-")
        offset_x, offset_y = LABEL_OFFSETS.get(offset_key, (0, 0))
        map_labels.append(
            f'<text x="{x_moment / (3 * area2) + offset_x:.1f}" '
            f'y="{y_moment / (3 * area2) + offset_y:.1f}" '
            f'text-anchor="middle" dominant-baseline="central" font-size="12" '
            f'font-weight="bold" fill="#fff" stroke="#000" stroke-width="4" '
            f'stroke-linejoin="round" paint-order="stroke">{escape(label)}</text>'
        )

    # Position legend on the right side with background box
    legend_items = []
    legend_x = MAP_WIDTH + PAD - 20
    legend_y = PAD + 20
    
    # Calculate legend dimensions for background box
    legend_title_text = "RBA Areas"
    legend_box_width = 155
    legend_box_height = 24 + len(GROUP_COLORS) * 22 + 10
    legend_box_x = legend_x - 10
    legend_box_y = legend_y - 5
    
    # Add background rectangle for legend
    legend_items.append(
        f'<rect x="{legend_box_x}" y="{legend_box_y}" width="{legend_box_width}" height="{legend_box_height}" '
        f'fill="#000" opacity="0.75" />'
    )
    
    legend_title = (
        f'<text x="{legend_x}" y="{legend_y+16}" font-size="16" font-weight="bold" fill="#fff">'
        f'{escape(legend_title_text)}</text>'
    )
    legend_items.append(legend_title)
    
    for index, (category, color) in enumerate(GROUP_COLORS.items()):
        item_y = legend_y + 28 + index * 22
        legend_items.append(
            f'<rect x="{legend_x}" y="{item_y}" width="16" height="16" fill="{color}" stroke="#fff" stroke-width="1"/>'
        )
        legend_items.append(
            f'<text x="{legend_x + 22}" y="{item_y + 12}" font-size="12" fill="#fff">{escape(category)}</text>'
        )
    legend = "\n".join(legend_items)

    panel_height = height
    defs_svg = (
        '<defs>'
        '<pattern id="oos-stripes" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(-45)">'
        '<line x1="0" y1="0" x2="0" y2="6" stroke="#262127" opacity="0.5" stroke-width="4"/>'
        '</pattern>'
        '</defs>'
    )
    svg = (
        f'<g transform="translate(0,{y0})">\n'
        f'{defs_svg}\n'
        f'<text x="{PAD}" y="26" font-size="18" font-weight="bold">{escape(title)}</text>\n'
        f'<g>\n' + "\n".join(paths) + "\n</g>\n"
        + "\n".join(map_labels) + "\n"
        + legend
        + "\n</g>\n"
    )
    return svg, panel_height


def main():
    regions = REGIONS
    features = load_counties()

    output_dir = Path(__file__).parent
    svg, height = panel(features, regions, COLORS, "GA Birding Discord Regions", 0, REGION_LABELS)
    width = MAP_WIDTH + 2 * PAD + 120
    out = output_dir / "georgia_regions.svg"
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" font-family="sans-serif" font-size="13" fill="#fff">\n'
        f'<rect width="100%" height="100%" fill="#262127"/>\n' + svg + "</svg>\n",
        encoding="utf-8",
    )
    print(f"Wrote {out} ({len(regions)} regions)")


if __name__ == "__main__":
    main()
