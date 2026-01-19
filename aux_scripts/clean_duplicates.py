#!/usr/bin/env python3
"""
Clean Duplicate Activity Files

This script scans the bulk_import folder and:
1. Deletes JSON sidecar files that have matching FIT files (e.g., from Analyzer.com exports)
2. Moves health/monitoring FIT files to a "health" subfolder
3. Finds duplicate activity files by comparing start timestamps
4. Deletes duplicates, keeping the preferred source

Source preference order for duplicates:
1. Garmin export files (email@domain_activityId.fit)
2. Other files (Intervals.icu format: YYYY-MM-DD-HH_MM-id.fit, etc.)

Usage:
    python clean_duplicates.py [--dry-run] [--tolerance SECONDS]

Options:
    --dry-run       Show what would happen without making changes
    --tolerance     Timestamp match tolerance in seconds (default: 5)
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# Add backend/app to path so we can import fitparse
script_dir = Path(__file__).parent
backend_app_dir = script_dir.parent / "backend" / "app"
sys.path.insert(0, str(backend_app_dir))

try:
    from fitparse import FitFile
except ImportError:
    print("Error: fitparse library not found.")
    print("Install it with: pip install fitparse")
    sys.exit(1)

# Default bulk import directory (relative to script location)
DEFAULT_BULK_IMPORT_DIR = script_dir.parent / "backend" / "app" / "data" / "activity_files" / "bulk_import"

# Timestamp tolerance for matching duplicates (in seconds)
# Activity files from the same workout should have identical start times,
# so a small tolerance (5 seconds) handles any minor discrepancies
DEFAULT_TOLERANCE_SECONDS = 5


def get_fit_start_time(filepath: Path) -> datetime | None:
    """
    Extract the start timestamp from a FIT activity file.
    Returns None for non-activity files (monitoring, settings, sleep, etc.)
    """
    try:
        fitfile = FitFile(str(filepath))

        # Only process activity files - they have session records
        # Non-activity files (monitoring, sleep, settings) don't have sessions
        for record in fitfile.get_messages():
            if record.name == "session":
                for field in record.fields:
                    if field.name == "start_time" and field.value:
                        return field.value

        # No session found = not an activity file, skip it
        return None

    except Exception as e:
        print(f"  Warning: Could not parse {filepath.name}: {e}")

    return None


def classify_source(filename: str) -> tuple[str, int]:
    """
    Classify the source of a file based on its filename pattern.
    Returns (source_name, priority) where lower priority = preferred.
    """
    # Garmin export: contains @ symbol (email prefix)
    if "@" in filename:
        return ("Garmin Export", 1)

    # Intervals.icu or similar: YYYY-MM-DD pattern
    if len(filename) > 10 and filename[4] == "-" and filename[7] == "-":
        return ("Intervals.icu", 2)

    # Unknown source
    return ("Unknown", 3)


def find_json_files(bulk_import_dir: Path) -> tuple[list[Path], list[Path]]:
    """
    Find JSON files and categorize them as sidecars or orphans.

    Returns (sidecars, orphans) where:
    - sidecars: JSON files that have matching FIT files (can be deleted)
    - orphans: JSON files without matching FIT files (need conversion)
    """
    json_files = list(bulk_import_dir.glob("*.json")) + list(bulk_import_dir.glob("*.JSON"))
    fit_files = set(f.stem.lower() for f in bulk_import_dir.glob("*.fit"))
    fit_files.update(f.stem.lower() for f in bulk_import_dir.glob("*.FIT"))

    sidecars = []
    orphans = []
    for json_file in json_files:
        if json_file.stem.lower() in fit_files:
            sidecars.append(json_file)
        else:
            orphans.append(json_file)

    return sidecars, orphans


ORPHAN_JSON_README = """Unsupported JSON Activity Files
================================

These JSON files are activity exports (likely from Suunto/Analyzer.com or
Intervals.icu) that don't have corresponding FIT files. Endurain only supports
importing FIT, GPX, and TCX formats, so these files cannot be imported directly.

Why are these files here?
-------------------------
These orphan JSON files typically fall into two categories:

1. Indoor/Non-GPS Activities: Activities like strength training, indoor cycling,
   or treadmill runs that have heart rate, duration, and other metrics but no
   GPS coordinates. Runalyzer/Analyzer.com often can't export these as FIT files
   even though the FIT format fully supports non-GPS activities.

2. Duplicate Exports: Some activities may already exist as FIT files but were
   exported with different Runalyzer activity IDs. Check if you already have
   activities on the same date/time that were successfully imported.

Why can't these be converted?
-----------------------------
The FIT format does NOT require GPS data - Garmin displays indoor workouts,
strength training, etc. without maps all the time. These JSON files contain
valid activity data (heart rate, duration, cadence, calories, sport type, etc.)
that could theoretically be converted to FIT format.

The limitation is that Runalyzer/Analyzer.com's export doesn't generate FIT
files for certain activity types, not that the data is unconvertible.

How to import these activities
------------------------------

Option 1: Use the JSON-to-FIT converter script (Recommended)
- Run: python aux_scripts/convert_json_to_fit.py
- This converts the JSON files to valid FIT format with HR, cadence, power, GPS
- The FIT files are created in the bulk_import folder ready for import
- Use --dry-run first to preview what will be converted

Option 2: Re-export from the original source
- Log into Suunto App / Movescount / Analyzer.com or wherever these activities
  originated
- Export the activities again, selecting FIT or "Original format" if available
- Some platforms allow bulk export of all activities

Option 3: Re-export from Intervals.icu
- If these activities are synced to Intervals.icu, you can download the original
  files from there
- Go to the activity page and look for a download/export option

Option 4: Manual import of key data
- If the above options fail, you could manually create activities in Endurain
  using the data visible in the JSON files (date, distance, duration, etc.)

Files in this folder
--------------------
"""


def find_duplicates(bulk_import_dir: Path, tolerance_seconds: int, move_health: bool = True) -> tuple[list, list]:
    """
    Scan directory for FIT files and group by start timestamp.
    Returns (duplicate_groups, health_files) where:
    - duplicate_groups: list of (timestamp, [(filepath, source, priority), ...])
    - health_files: list of filepaths that are non-activity (health/monitoring) files
    """
    fit_files = list(bulk_import_dir.glob("*.fit")) + list(bulk_import_dir.glob("*.FIT"))

    if not fit_files:
        print(f"No FIT files found in {bulk_import_dir}")
        return [], []

    print(f"Scanning {len(fit_files)} FIT files...")

    # Parse all files and get timestamps (only activity files have sessions)
    file_times = []
    health_files = []
    for filepath in fit_files:
        start_time = get_fit_start_time(filepath)
        if start_time:
            source, priority = classify_source(filepath.name)
            file_times.append((filepath, start_time, source, priority))
        else:
            health_files.append(filepath)

    print(f"Found {len(file_times)} activity files and {len(health_files)} health/monitoring files.")

    # Group files by similar timestamps
    tolerance = timedelta(seconds=tolerance_seconds)
    groups = []
    used = set()

    # Sort by timestamp for efficient grouping
    file_times.sort(key=lambda x: x[1])

    for i, (filepath, timestamp, source, priority) in enumerate(file_times):
        if i in used:
            continue

        group = [(filepath, source, priority)]
        used.add(i)

        # Find all files within tolerance
        for j, (other_path, other_time, other_source, other_priority) in enumerate(file_times):
            if j in used:
                continue
            if abs((timestamp - other_time).total_seconds()) <= tolerance_seconds:
                group.append((other_path, other_source, other_priority))
                used.add(j)

        if len(group) > 1:
            groups.append((timestamp, group))

    return groups, health_files


def display_duplicates(groups: list) -> tuple[list, list]:
    """
    Display duplicate groups and determine which files to keep/delete.
    Returns (files_to_keep, files_to_delete)
    """
    files_to_keep = []
    files_to_delete = []

    print(f"\n{'='*70}")
    print(f"Found {len(groups)} duplicate groups:")
    print(f"{'='*70}\n")

    for timestamp, group in groups:
        # Sort by priority (lower = preferred)
        group.sort(key=lambda x: x[2])

        keep = group[0]
        delete = group[1:]

        files_to_keep.append(keep[0])
        files_to_delete.extend([f[0] for f in delete])

        print(f"Activity at {timestamp}:")
        print(f"  KEEP:   {keep[0].name} ({keep[1]})")
        for filepath, source, _ in delete:
            print(f"  DELETE: {filepath.name} ({source})")
        print()

    return files_to_keep, files_to_delete


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Clean duplicate FIT files from bulk import folder")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    parser.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE_SECONDS,
                        help=f"Timestamp match tolerance in seconds (default: {DEFAULT_TOLERANCE_SECONDS})")
    parser.add_argument("--dir", type=str, default=None,
                        help="Bulk import directory (default: backend/app/data/activity_files/bulk_import)")

    args = parser.parse_args()

    bulk_import_dir = Path(args.dir) if args.dir else DEFAULT_BULK_IMPORT_DIR

    if not bulk_import_dir.exists():
        print(f"Error: Directory not found: {bulk_import_dir}")
        sys.exit(1)

    print(f"Bulk Import Directory: {bulk_import_dir}")
    print(f"Timestamp Tolerance: {args.tolerance} seconds")
    if args.dry_run:
        print("Mode: DRY RUN (no files will be deleted)")
    print()

    # Find JSON files (sidecars with matching FIT, and orphans without)
    json_sidecars, json_orphans = find_json_files(bulk_import_dir)

    # Find duplicates and health files
    groups, health_files = find_duplicates(bulk_import_dir, args.tolerance)

    # Display JSON sidecar files that will be deleted
    if json_sidecars:
        print(f"\n{'='*70}")
        print(f"JSON sidecar files to delete (matching FIT files exist):")
        print(f"{'='*70}")
        for f in json_sidecars[:10]:  # Show first 10
            print(f"  {f.name}")
        if len(json_sidecars) > 10:
            print(f"  ... and {len(json_sidecars) - 10} more")
        print()

    # Display orphan JSON files that will be moved
    if json_orphans:
        orphan_dir = bulk_import_dir / "unsupported_json_format"
        print(f"\n{'='*70}")
        print(f"Orphan JSON files to move to {orphan_dir.name}/ (no matching FIT):")
        print(f"{'='*70}")
        for f in json_orphans[:10]:  # Show first 10
            print(f"  {f.name}")
        if len(json_orphans) > 10:
            print(f"  ... and {len(json_orphans) - 10} more")
        print()

    # Display health files that will be moved
    if health_files:
        health_dir = bulk_import_dir / "health"
        print(f"\n{'='*70}")
        print(f"Health/monitoring files to move to {health_dir.name}/:")
        print(f"{'='*70}")
        for f in health_files[:10]:  # Show first 10
            print(f"  {f.name}")
        if len(health_files) > 10:
            print(f"  ... and {len(health_files) - 10} more")
        print()

    # Display duplicate activity files
    files_to_keep = []
    files_to_delete = []
    if groups:
        files_to_keep, files_to_delete = display_duplicates(groups)
    else:
        print("\nNo duplicate activity files found!")

    # Summary
    print(f"{'='*70}")
    print(f"Summary:")
    print(f"  JSON sidecar files to delete:   {len(json_sidecars)}")
    print(f"  Orphan JSON files to move:      {len(json_orphans)}")
    print(f"  Health files to move:           {len(health_files)}")
    print(f"  Duplicate activities to keep:   {len(files_to_keep)}")
    print(f"  Duplicate activities to delete: {len(files_to_delete)}")
    print(f"{'='*70}\n")

    if args.dry_run:
        print("Dry run complete. No files were modified.")
        print("Run without --dry-run to delete sidecars, move health files, and delete duplicates.")
        return

    if not json_sidecars and not json_orphans and not health_files and not files_to_delete:
        print("Nothing to do!")
        return

    # Prompt for confirmation
    response = input("Do you want to proceed? (yes/no): ").strip().lower()

    if response != "yes":
        print("Aborted. No files were modified.")
        return

    # Delete JSON sidecar files
    json_deleted_count = 0
    if json_sidecars:
        print(f"\nDeleting JSON sidecar files...")
        for filepath in json_sidecars:
            try:
                filepath.unlink()
                json_deleted_count += 1
            except Exception as e:
                print(f"Error deleting {filepath.name}: {e}")
        print(f"Deleted {json_deleted_count} JSON sidecar files.")

    # Move orphan JSON files to subfolder with README
    json_moved_count = 0
    if json_orphans:
        orphan_dir = bulk_import_dir / "unsupported_json_format"
        orphan_dir.mkdir(exist_ok=True)
        print(f"\nMoving orphan JSON files to {orphan_dir}/...")

        # Create README with list of files
        readme_content = ORPHAN_JSON_README
        for f in sorted(json_orphans, key=lambda x: x.name):
            readme_content += f"- {f.name}\n"

        readme_path = orphan_dir / "README.txt"
        readme_path.write_text(readme_content)
        print(f"Created {readme_path.name} with conversion instructions.")

        for filepath in json_orphans:
            try:
                dest = orphan_dir / filepath.name
                filepath.rename(dest)
                json_moved_count += 1
            except Exception as e:
                print(f"Error moving {filepath.name}: {e}")
        print(f"Moved {json_moved_count} orphan JSON files.")

    # Move health files to subfolder
    moved_count = 0
    if health_files:
        health_dir = bulk_import_dir / "health"
        health_dir.mkdir(exist_ok=True)
        print(f"\nMoving health files to {health_dir}/...")
        for filepath in health_files:
            try:
                dest = health_dir / filepath.name
                filepath.rename(dest)
                moved_count += 1
            except Exception as e:
                print(f"Error moving {filepath.name}: {e}")
        print(f"Moved {moved_count} health files.")

    # Delete duplicate activity files
    deleted_count = 0
    if files_to_delete:
        print(f"\nDeleting duplicate activity files...")
        for filepath in files_to_delete:
            try:
                filepath.unlink()
                print(f"Deleted: {filepath.name}")
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting {filepath.name}: {e}")

    print(f"\nDone! Deleted {json_deleted_count} JSON sidecars, moved {json_moved_count} orphan JSONs, moved {moved_count} health files, deleted {deleted_count} duplicate activities.")


if __name__ == "__main__":
    main()
