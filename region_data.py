"""Load and validate shared county-to-region data."""

import json
import re
from pathlib import Path

DATA_PATH = Path(__file__).with_name("regions.json")
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))

if DATA.get("schema_version") != 1:
    raise ValueError(f"Unsupported region data schema: {DATA.get('schema_version')!r}")

REGION_LABELS = DATA["metadata"]["region_labels"]
REGION_GROUPS = DATA["metadata"]["region_groups"]
GROUP_COLORS = DATA["metadata"]["group_colors"]
REGION_COUNTIES = DATA["regions"]

REGIONS: dict[str, list[str]] = {}
COUNTY_REGION: dict[str, str] = {}
COUNTY_GEOIDS: dict[str, str] = {}
COUNTY_NAMES_BY_GEOID: dict[str, str] = {}

for region, counties in REGION_COUNTIES.items():
    if region not in REGION_LABELS:
        raise ValueError(f"Region {region!r} is missing a label")
    REGIONS[region] = []
    for county in counties:
        geoid = county["geoid"]
        name = county["name"]
        if not re.fullmatch(r"\d{5}", geoid):
            raise ValueError(f"Invalid county GEOID for {name!r}: {geoid!r}")
        if geoid in COUNTY_REGION:
            raise ValueError(f"County GEOID {geoid} is assigned more than once")
        key = name.casefold()
        if key in COUNTY_GEOIDS:
            raise ValueError(f"County name {name!r} is assigned more than once")
        COUNTY_REGION[geoid] = region
        COUNTY_GEOIDS[key] = geoid
        COUNTY_NAMES_BY_GEOID[geoid] = name
        REGIONS[region].append(name)

categorized_regions = [
    region for category_regions in REGION_GROUPS.values() for region in category_regions
]
if len(categorized_regions) != len(set(categorized_regions)):
    raise ValueError("A region is assigned to multiple categories")
if set(categorized_regions) != set(REGIONS):
    raise ValueError("Every region must be assigned to exactly one category")
if set(REGION_LABELS) != set(REGIONS):
    raise ValueError("Region labels and county assignments must have matching regions")
