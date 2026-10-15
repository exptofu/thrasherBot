#!/usr/bin/env python3
"""Summarize database-stored bird submissions by Georgia region/category.

This script treats every record in sightings.db as a "rare" submission for the
purposes of the report. That matches the bot's actual behavior: it stores only
notable records that were accepted into the database, rather than relying on a
separate rare_birds.txt list.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from georgia_map import REGIONS, REGION_GROUPS


def normalize_species(name: str) -> str:
    return " ".join(str(name).replace("’", "'").lower().split())


def summarize_db_sightings(db_path: Path) -> tuple[dict, dict]:
    county_to_region = {county.lower(): region for region, counties in REGIONS.items() for county in counties}
    region_to_category = {
        region: category for category, regions in REGION_GROUPS.items() for region in regions
    }

    region_stats: dict[str, dict] = defaultdict(
        lambda: {"stored_sightings": 0, "checklists": set(), "species": set()}
    )
    category_stats: dict[str, dict] = defaultdict(
        lambda: {"stored_sightings": 0, "checklists": set(), "species": set()}
    )

    with sqlite3.connect(db_path) as conn:
        for sub_id, _, checklist_id, _, data in conn.execute(
            "SELECT sub_id, species_code, checklist_id, scope, data FROM sightings"
        ):
            try:
                record = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue

            county = (record.get("subnational2Name") or "").strip()
            if not county:
                continue

            region = county_to_region.get(county.lower())
            if not region:
                continue

            category = region_to_category.get(region)
            species = normalize_species(record.get("comName") or "")
            if not species:
                continue

            region_stats[region]["stored_sightings"] += 1
            region_stats[region]["species"].add(species)

            checklist_key = row_checklist_id(sub_id, checklist_id, record)
            region_stats[region]["checklists"].add(checklist_key)

            if category:
                category_stats[category]["stored_sightings"] += 1
                category_stats[category]["species"].add(species)
                category_stats[category]["checklists"].add(checklist_key)

    for stats in region_stats.values():
        stats["checklists"] = len(stats.pop("checklists"))
        stats["species_count"] = len(stats.pop("species"))
    for stats in category_stats.values():
        stats["checklists"] = len(stats.pop("checklists"))
        stats["species_count"] = len(stats.pop("species"))

    return dict(region_stats), dict(category_stats)


def row_checklist_id(sub_id: str, checklist_id: str, record: dict) -> str:
    if sub_id.startswith("S"):
        return sub_id
    if checklist_id:
        return checklist_id
    return str(record.get("checklistId") or record.get("subId") or sub_id)


def print_summary(title: str, stats: dict[str, dict], *, is_category: bool = False) -> None:
    rows = []
    for name, values in stats.items():
        rows.append(
            {
                "name": name,
                "stored_sightings": values.get("stored_sightings", 0),
                "checklists": values.get("checklists", 0),
                "species_count": values.get("species_count", 0),
            }
        )

    rows.sort(key=lambda row: (-row["stored_sightings"], -row["checklists"], row["name"]))

    header = (
        f"{'Category' if is_category else 'Region':<24}  "
        f"{'stored_sightings':>16}  {'checklists':>12}  {'species':>8}"
    )
    print(f"\n{title}")
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['name']:<24}  "
            f"{row['stored_sightings']:>16}  "
            f"{row['checklists']:>12}  "
            f"{row['species_count']:>8}"
        )

    if not rows:
        print("No stored sightings found.")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Summarize database-stored bird submissions by Georgia region/category.")
    parser.add_argument("--db", type=Path, default=root / "sightings.db", help="Path to sightings.db")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    region_stats, category_stats = summarize_db_sightings(args.db)
    print_summary("Stored sightings by region", region_stats)
    print_summary("Stored sightings by category", category_stats, is_category=True)


if __name__ == "__main__":
    main()
