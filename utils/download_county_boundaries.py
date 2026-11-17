"""Download configured Census county boundaries for the Pages site."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REGIONS_PATH = ROOT / "regions.json"
DEFAULT_OUTPUT_PATH = ROOT / "site" / "county-boundaries.geojson"
CENSUS_QUERY_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/State_County/MapServer/1/query"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Census county boundaries configured in regions.json."
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=REGIONS_PATH,
        help=f"Shared region data file (default: {REGIONS_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output GeoJSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--gzip-output",
        type=Path,
        help="Compressed output path (default: <output>.gz)",
    )
    return parser.parse_args()


def configured_geoids(regions_path: Path) -> list[str]:
    with regions_path.open(encoding="utf-8") as regions_file:
        data = json.load(regions_file)

    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("regions"), dict)
    ):
        raise ValueError(f"{regions_path} has an unsupported region data schema")

    geoids: set[str] = set()
    for region, counties in data["regions"].items():
        if not isinstance(counties, list):
            raise ValueError(f"Region {region!r} must contain a county list")
        for county in counties:
            if not isinstance(county, dict):
                raise ValueError(f"Region {region!r} contains an invalid county record")
            geoid = str(county.get("geoid", ""))
            if not re.fullmatch(r"\d{5}", geoid):
                raise ValueError(f"Invalid county GEOID in region {region!r}: {geoid!r}")
            if geoid in geoids:
                raise ValueError(f"Duplicate county GEOID: {geoid}")
            geoids.add(geoid)

    if not geoids:
        raise ValueError(f"No county GEOIDs found in {regions_path}")
    return sorted(geoids)


def fetch_county_features(geoids: list[str]) -> list[dict]:
    where_clause = f"GEOID IN ({','.join(repr(geoid) for geoid in geoids)})"
    params = urlencode(
        {
            "where": where_clause,
            "outFields": "GEOID,NAME",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        }
    )
    request = Request(
        f"{CENSUS_QUERY_URL}?{params}",
        headers={"User-Agent": "thrasherBot county-boundary build"},
    )
    with urlopen(request, timeout=120) as response:
        data = json.load(response)

    if (
        not isinstance(data, dict)
        or data.get("type") != "FeatureCollection"
        or not isinstance(data.get("features"), list)
    ):
        raise ValueError("Census response is not a GeoJSON FeatureCollection")

    expected_geoids = set(geoids)
    features_by_geoid: dict[str, dict] = {}
    for feature in data["features"]:
        if not isinstance(feature, dict):
            raise ValueError("Census response contains an invalid feature")
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            raise ValueError("Census response contains invalid feature properties")
        geoid = str(properties.get("GEOID", ""))
        if geoid not in expected_geoids:
            continue
        if geoid in features_by_geoid:
            raise ValueError(f"Census response contains duplicate GEOID {geoid}")

        geometry = feature.get("geometry")
        if (
            not isinstance(geometry, dict)
            or geometry.get("type") not in {"Polygon", "MultiPolygon"}
            or not geometry.get("coordinates")
        ):
            raise ValueError(f"Census response has invalid geometry for GEOID {geoid}")

        name = re.sub(r"\s+County$", "", str(properties.get("NAME", "")), flags=re.IGNORECASE)
        if not name:
            raise ValueError(f"Census response has no county name for GEOID {geoid}")
        features_by_geoid[geoid] = {
            "type": "Feature",
            "properties": {"GEOID": geoid, "NAME": name},
            "geometry": {
                **geometry,
                "coordinates": round_coordinates(geometry["coordinates"]),
            },
        }

    missing_geoids = expected_geoids - features_by_geoid.keys()
    if missing_geoids:
        raise ValueError(
            "Census response is missing configured GEOIDs: "
            + ", ".join(sorted(missing_geoids))
        )
    return [features_by_geoid[geoid] for geoid in geoids]


def round_coordinates(coordinates: list | int | float) -> list | int | float:
    if isinstance(coordinates, list):
        return [round_coordinates(value) for value in coordinates]
    if isinstance(coordinates, (int, float)):
        return round(coordinates, 5)
    raise ValueError("Census response contains invalid geometry coordinates")


def main() -> int:
    args = parse_args()
    try:
        geoids = configured_geoids(args.regions)
        features = fetch_county_features(geoids)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        geojson = json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        args.output.write_bytes(geojson + b"\n")
        gzip_output = args.gzip_output or args.output.with_name(f"{args.output.name}.gz")
        gzip_output.parent.mkdir(parents=True, exist_ok=True)
        gzip_output.write_bytes(gzip.compress(geojson, compresslevel=9, mtime=0))
    except (OSError, json.JSONDecodeError, URLError, ValueError) as error:
        print(f"County boundary download failed: {error}", file=sys.stderr)
        return 1

    print(
        f"Wrote {len(features)} county boundaries to {args.output} "
        f"and {gzip_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
