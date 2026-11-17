"""Render georgia_regions.svg from the region/category layout used by the bot.

Stdlib only. County outlines come from the public plotly/datasets GeoJSON (Census data).
Usage: python georgia_map.py
"""
import json
import math
import re
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from region_data import (
    COUNTY_REGION,
    GROUP_COLORS,
    REGION_COUNTIES,
    REGION_GROUPS,
    REGION_LABELS,
    REGIONS,
)

GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
MAP_WIDTH = 620
PAD = 60

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
    features_by_geoid = {
        feature_geoid(feature): feature
        for feature in data["features"]
        if feature_geoid(feature) is not None
    }
    missing = set(COUNTY_REGION) - set(features_by_geoid)
    if missing:
        raise ValueError(f"Configured county GEOIDs missing from GeoJSON: {sorted(missing)}")
    return [features_by_geoid[geoid] for geoid in COUNTY_REGION]


def feature_geoid(feature: dict) -> str | None:
    """Return a feature's five-digit Census county GEOID."""
    properties = feature.get("properties", {})
    value = feature.get("id") or properties.get("GEOID")
    if value is not None and str(value).isdigit():
        return str(value).zfill(5)
    census_id = properties.get("GEO_ID", "")
    match = re.search(r"(\d{5})$", str(census_id))
    if match:
        return match.group(1)
    state = properties.get("STATE") or properties.get("STATEFP")
    county = properties.get("COUNTY") or properties.get("COUNTYFP")
    if state is not None and county is not None:
        return f"{str(state).zfill(2)}{str(county).zfill(3)}"
    return None


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
    county_region = {
        county["geoid"]: region
        for region, counties in REGION_COUNTIES.items()
        for county in counties
    }

    feature_geoids = [feature_geoid(feature) for feature in features]
    if None in feature_geoids or len(feature_geoids) != len(set(feature_geoids)):
        raise SystemExit("County features have missing or duplicate GEOIDs")
    if set(feature_geoids) != set(county_region):
        raise SystemExit(f"County GEOID mismatch: {sorted(set(feature_geoids) ^ set(county_region))}")
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
        return (p[0] * kx - min_x) * scale + PAD*.7, (max_y - p[1]) * scale + PAD*1.2

    paths = []
    centroids = {region: [0.0, 0.0, 0.0] for region in regions}
    county_segments: dict[str, set[tuple[tuple[float, float], tuple[float, float]]]] = {}
    oos_counties = {geoid for geoid in county_region if not geoid.startswith("13")}
    
    # Count counties per region for detecting multi-county regions
    region_county_count = {}
    for geoid, region in county_region.items():
        region_county_count[region] = region_county_count.get(region, 0) + 1
    
    # Track region-to-region segments for lower opacity
    # Using a list of regions for each segment to detect same-region internal borders
    region_segment_map_list = {}

    for f in sorted(features, key=lambda f: f["properties"]["NAME"]):
        name = f["properties"]["NAME"]
        geoid = feature_geoid(f)
        region = county_region[geoid]
        projected = [[project(p) for p in r] for r in rings(f["geometry"])]
        county_segments[geoid] = set()
        for ring in projected:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                cross = x1 * y2 - x2 * y1
                centroids[region][0] += cross
                centroids[region][1] += (x1 + x2) * cross
                centroids[region][2] += (y1 + y2) * cross
                segment = normalize_segment((x1, y1), (x2, y2))
                county_segments[geoid].add(segment)
                # Track segments by region (use list to detect same-region internal borders)
                if segment not in region_segment_map_list:
                    region_segment_map_list[segment] = []
                region_segment_map_list[segment].append(region)
        d = " ".join(
            "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in r) + "Z" for r in projected
        )
        
        # Use pattern fill for out-of-state counties, solid color for Georgia
        fill_color = colors[region]
        if geoid in oos_counties:
            paths.append(
                f'<path d="{d}" fill="{fill_color}" stroke="#f2f2f2" stroke-width="0.8" stroke-linejoin="round"><title>{escape(name)}</title></path>'
            )
            paths.append(
                f'<path d="{d}" fill="url(#oos-stripes)" stroke="none" opacity="0.85"><title>{escape(name)} (Out of state)</title></path>'
            )
        else:
            paths.append(
                f'<path d="{d}" fill="{fill_color}" stroke="none"><title>{escape(name)}</title></path>'
            )

    # Build segment map to determine which borders should be drawn and with what opacity
    segment_map: dict[tuple[tuple[float, float], tuple[float, float]], set[str]] = {}
    for geoid, segments in county_segments.items():
        for segment in segments:
            segment_map.setdefault(segment, set()).add(geoid)

    # Categorize segments into different types
    state_boundary_segments: list[tuple[float, float, float, float]] = []
    ga_to_oos_segments: list[tuple[float, float, float, float]] = []
    region_boundary_segments: list[tuple[float, float, float, float]] = []
    internal_region_segments: list[tuple[float, float, float, float]] = []
    
    for segment, counties in segment_map.items():
        (x1, y1), (x2, y2) = segment
        
        if len(counties) == 1:
            # External boundary (state edge)
            geoid = list(counties)[0]
            if geoid not in oos_counties:
                state_boundary_segments.append((x1, y1, x2, y2))
        elif len(counties) == 2:
            geoid1, geoid2 = list(counties)
            region1 = county_region[geoid1]
            region2 = county_region[geoid2]
            is_oos_1 = geoid1 in oos_counties
            is_oos_2 = geoid2 in oos_counties
            
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
            f'stroke-linecap="butt" stroke-linejoin="round" opacity="0.7"/>'
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
    legend_x = MAP_WIDTH + PAD - 40
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
        f'<text x="{PAD*.7}" y="45" font-size="24" font-weight="bold">{escape(title)}</text>\n'
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
    width = MAP_WIDTH + 1 * PAD + 120
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
