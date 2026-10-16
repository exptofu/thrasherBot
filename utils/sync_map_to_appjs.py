#!/usr/bin/env python3
"""Sync the canonical Georgia region metadata from georgia_map.py into app.js."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "georgia_map.py"
APP_PATH = ROOT / "app.js"


def extract_dict(name: str) -> dict:
    source = MAP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAP_PATH))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = ast.literal_eval(node.value)
                    if isinstance(value, dict):
                        return value
    raise ValueError(f"Could not find {name!r} in {MAP_PATH}")


def render_js_list(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(item) for item in values) + "]"


def render_js_object(name: str, data: dict[str, object]) -> str:
    lines = [f"const {name} = {{"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f'  {json.dumps(key)}: {render_js_list(value)},')
        elif isinstance(value, str):
            lines.append(f'  {json.dumps(key)}: {json.dumps(value)},')
        else:
            raise TypeError(f"Unsupported value type for {name}.{key}: {type(value)!r}")
    lines.append("};")
    return "\n".join(lines)


def render_county_lookup_block() -> str:
    return """const COUNTY_TO_REGION = {};
for (const [regionSlug, counties] of Object.entries(REGIONS)) {
  for (const county of counties) {
    COUNTY_TO_REGION[county.toLowerCase()] = regionSlug;
  }
}

const COUNTY_TO_CATEGORY = {};
for (const [categoryName, regionSlugs] of Object.entries(REGION_GROUPS)) {
  for (const regionSlug of regionSlugs) {
    for (const county of REGIONS[regionSlug] || []) {
      COUNTY_TO_CATEGORY[county.toLowerCase()] = categoryName;
    }
  }
}
"""


def sync_app_js() -> bool:
    regions = extract_dict("REGIONS")
    region_groups = extract_dict("REGION_GROUPS")
    region_labels = extract_dict("REGION_LABELS")

    new_block = "\n\n".join(
        [
            render_js_object("REGIONS", regions),
            render_js_object("REGION_GROUPS", region_groups),
            render_county_lookup_block().rstrip(),
            render_js_object("REGION_LABELS", region_labels),
        ]
    ) + "\n"

    original = APP_PATH.read_text(encoding="utf-8")
    start = original.index("const REGIONS = {")
    end = original.index("let countyGeoJson = null;")

    updated = original[:start] + new_block + original[end:]
    if updated == original:
        return False

    APP_PATH.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    changed = sync_app_js()
    if changed:
        print(f"Synced region definitions from {MAP_PATH.name} to {APP_PATH.name}.")
    else:
        print(f"{APP_PATH.name} already matches the region definitions from {MAP_PATH.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
