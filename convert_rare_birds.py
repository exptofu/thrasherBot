"""Build a Python mapping of rare bird names to their eBird six-letter codes.

Run this any time the species list changes:
    python convert_rare_birds.py
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from urllib.request import Request, urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
RARE_BIRDS_PATH = ROOT / "rare_birds.txt"
OUTPUT_PATH = ROOT / "rare_birds_codes.py"


def normalize_species(name: str) -> str:
    return " ".join(name.replace("’", "'").lower().split())


def fetch_species_lookup() -> dict[str, str]:
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("EBIRD_API_KEY")
    if not api_key:
        raise RuntimeError("EBIRD_API_KEY must be set before running this conversion script.")

    req = Request(
        "https://api.ebird.org/v2/ref/taxonomy/ebird",
        headers={"x-ebirdapitoken": api_key},
    )
    with urlopen(req, timeout=30) as response:
        content = response.read().decode("utf-8")

    lookup: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        common_name = (row.get("COMMON_NAME") or row.get("COM_NAME") or "").strip()
        species_code = (row.get("SPECIES_CODE") or "").strip()
        if not common_name or not species_code:
            continue
        normalized = normalize_species(common_name)
        if normalized:
            lookup.setdefault(normalized, species_code)
    return lookup


def main() -> None:
    lookup = fetch_species_lookup()
    codes: dict[str, str] = {}
    missing: list[str] = []

    for line in RARE_BIRDS_PATH.read_text(encoding="utf-8").splitlines():
        species = normalize_species(line)
        if not species:
            continue
        code = lookup.get(species)
        if not code:
            missing.append(species)
            continue
        codes[species] = code

    if missing:
        print("Missing eBird species codes for:")
        for species in sorted(missing):
            print(f" - {species}")

    lines = [
        "RARE_BIRD_CODES = {",
    ]
    for species in sorted(codes):
        lines.append(f'    {species!r}: {codes[species]!r},')
    lines.extend([
        "}",
        "",
        "RARE_BIRDS = set(RARE_BIRD_CODES)",
        "",
    ])
    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(codes)} rare bird mappings to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
