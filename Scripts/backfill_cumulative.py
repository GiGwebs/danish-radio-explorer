#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Backfill the cumulative All-Stations playlist from historical Combined/All CSVs.

This script replays all dated files under:
  <PROJECT_ROOT>/Outputs/Combined/All/Combined_All_All_Stations_YYYY-MM-DD.csv
into the cumulative CSV maintained by radio_playlist_consolidator._update_cumulative_playlist.

Usage:
  python Scripts/backfill_cumulative.py [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--dry-run]

Notes:
- It processes files in ascending date order.
- On each step it calls _update_cumulative_playlist to update stable and snapshot files,
  so you will have snapshots for each processed day unless --dry-run is set.
- Safe to re-run; updates are idempotent by Artist/Title key.
"""
from __future__ import annotations

import os
import sys
import re
from datetime import datetime
from pathlib import Path
import pandas as pd

# Import consolidator functions
THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR
BASE_DIR = SCRIPTS_DIR.parent
COMBINED_DIR = BASE_DIR / "Outputs" / "Combined"
ALL_DIR = COMBINED_DIR / "All"

# Allow importing the consolidator module
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import radio_playlist_consolidator as rpc  # type: ignore


def _parse_args(argv: list[str]):
    start = None
    end = None
    dry = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry = True
            i += 1
            continue
        if a in ("--start", "-s") and i + 1 < len(argv):
            start = argv[i + 1]
            i += 2
            continue
        if a in ("--end", "-e") and i + 1 < len(argv):
            end = argv[i + 1]
            i += 2
            continue
        if a.startswith("--start="):
            start = a.split("=", 1)[1]
            i += 1
            continue
        if a.startswith("--end="):
            end = a.split("=", 1)[1]
            i += 1
            continue
        i += 1
    return start, end, dry


def _extract_date_from_name(p: Path) -> str | None:
    m = re.search(r"(20\d{2}-[01]\d-[0-3]\d)", p.name)
    return m.group(1) if m else None


def main(argv: list[str]) -> int:
    start, end, dry = _parse_args(argv)
    if not ALL_DIR.exists():
        print(f"Missing Combined/All directory: {ALL_DIR}")
        return 2

    files = sorted([p for p in ALL_DIR.glob("Combined_All_All_Stations_*.csv") if p.is_file()])
    if not files:
        print("No historical Combined All files found.")
        return 0

    # Filter by date range if provided
    def _in_range(d: str) -> bool:
        if start and d < start:
            return False
        if end and d > end:
            return False
        return True

    steps = []
    for p in files:
        d = _extract_date_from_name(p)
        if not d:
            continue
        if _in_range(d):
            steps.append((d, p))

    steps.sort(key=lambda t: t[0])  # ascending by date

    if not steps:
        print("No files match the provided date range.")
        return 0

    print(f"Backfilling cumulative from {len(steps)} day(s)...")
    stations_str = "All_Stations"

    for date_str, path in steps:
        try:
            df = pd.read_csv(path)
        except Exception as e:
            print(f"Skip {path.name}: failed to read CSV: {e}")
            continue
        if df.empty:
            print(f"Skip {path.name}: empty dataframe")
            continue
        print(f"- Applying {path.name} ({len(df)} rows)")
        if dry:
            # Resolve Artist/Title for a small preview
            preview = df.head(3)[[c for c in df.columns if c in ("Artist", "Title", "Track")]]
            print(preview.to_string(index=False))
            continue
        try:
            # Reuse the consolidator's cumulative updater for exact same schema/logic
            rpc._update_cumulative_playlist(df, str(COMBINED_DIR), stations_str, date_str)
        except Exception as e:
            print(f"Warning: failed to update cumulative for {path.name}: {e}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
