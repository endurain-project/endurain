#!/usr/bin/env python3
"""
Clean Duplicate Activity Files

This script scans the bulk_import folder and:
1. Moves health/monitoring FIT files to a "health" subfolder
2. Finds duplicate activity files by comparing start timestamps
3. Deletes duplicates, keeping the preferred source

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

    # Find duplicates and health files
    groups, health_files = find_duplicates(bulk_import_dir, args.tolerance)

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
    print(f"  Health files to move: {len(health_files)}")
    print(f"  Duplicate activities to keep:   {len(files_to_keep)}")
    print(f"  Duplicate activities to delete: {len(files_to_delete)}")
    print(f"{'='*70}\n")

    if args.dry_run:
        print("Dry run complete. No files were modified.")
        print("Run without --dry-run to move health files and delete duplicates.")
        return

    if not health_files and not files_to_delete:
        print("Nothing to do!")
        return

    # Prompt for confirmation
    response = input("Do you want to proceed? (yes/no): ").strip().lower()

    if response != "yes":
        print("Aborted. No files were modified.")
        return

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

    print(f"\nDone! Moved {moved_count} health files, deleted {deleted_count} duplicate activities.")


if __name__ == "__main__":
    main()
