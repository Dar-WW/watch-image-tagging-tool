#!/usr/bin/env python3
"""
Separate back view images into dedicated folders.

Transforms:
  downloaded_images/PATEK_nam_008/PATEK_nam_008_06_back_q3.jpg
  -> downloaded_images/PATEK_backnam_008/PATEK_nam_008_06_back_q3.jpg

Usage:
  # Dry run (preview changes)
  python separate_back_views.py --dry-run

  # Actually move files
  python separate_back_views.py

  # Copy instead of move
  python separate_back_views.py --copy

  # Specify custom images directory
  python separate_back_views.py --images-dir /path/to/downloaded_images
"""

import os
import re
import shutil
import argparse
from collections import defaultdict
from typing import Optional, Tuple

# Regex patterns for back views
PATTERN_WITH_QUALITY = r'^([A-Z]+)_([a-z]+)_(\d{3})_(\d{2})_(back)_q([123])\.jpg$'
PATTERN_LEGACY = r'^([A-Z]+)_([a-z]+)_(\d{3})_(\d{2})_(back)\.jpg$'


def parse_back_view_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    """Parse back view filename and extract brand, model, watch_num.

    Args:
        filename: Image filename (e.g., "PATEK_nam_008_06_back_q3.jpg")

    Returns:
        Tuple of (brand, model, watch_num) or None if not a back view

    Examples:
        >>> parse_back_view_filename("PATEK_nam_008_06_back_q3.jpg")
        ("PATEK", "nam", "008")
        >>> parse_back_view_filename("PATEK_nam_008_06_face_q3.jpg")
        None
    """
    # Try pattern with quality tag first
    match = re.match(PATTERN_WITH_QUALITY, filename)
    if match:
        return (match.group(1), match.group(2), match.group(3))

    # Try legacy pattern without quality tag
    match = re.match(PATTERN_LEGACY, filename)
    if match:
        return (match.group(1), match.group(2), match.group(3))

    return None


def get_target_folder_name(brand: str, model: str, watch_num: str) -> str:
    """Construct target folder name: BRAND_backMODEL_NUM.

    Args:
        brand: Brand name in uppercase (e.g., "PATEK")
        model: Model identifier in lowercase (e.g., "nam")
        watch_num: Three-digit watch number (e.g., "008")

    Returns:
        Target folder name (e.g., "PATEK_backnam_008")

    Examples:
        >>> get_target_folder_name("PATEK", "nam", "008")
        "PATEK_backnam_008"
    """
    return f"{brand}_back{model}_{watch_num}"


def process_images(images_dir: str, dry_run: bool, copy: bool, verbose: bool):
    """Main processing logic to separate back view images.

    Args:
        images_dir: Path to downloaded_images directory
        dry_run: If True, preview changes without moving files
        copy: If True, copy files instead of moving
        verbose: If True, show detailed file operations
    """
    if not os.path.isdir(images_dir):
        print(f"Error: Images directory not found: {images_dir}")
        return

    # Statistics tracking
    total_images = 0
    back_views_found = 0
    files_processed = 0
    errors = []
    folders_created = set()

    # Track files per watch for summary
    files_by_watch = defaultdict(list)

    operation = "COPY" if copy else "MOVE"
    mode_str = " (DRY RUN)" if dry_run else ""

    print(f"Back View Separation Tool{mode_str}")
    print("=" * 50)
    print(f"Images directory: {images_dir}")
    print(f"Operation: {operation}")
    print(f"Verbose: {verbose}")
    print()

    # Walk through all subdirectories
    for root, dirs, files in os.walk(images_dir):
        for filename in files:
            # Only process .jpg files
            if not filename.lower().endswith('.jpg'):
                continue

            total_images += 1
            source_path = os.path.join(root, filename)

            # Parse filename to check if it's a back view
            parsed = parse_back_view_filename(filename)
            if parsed is None:
                continue

            back_views_found += 1
            brand, model, watch_num = parsed

            # Construct target folder and path
            target_folder = get_target_folder_name(brand, model, watch_num)
            target_dir = os.path.join(images_dir, target_folder)
            target_path = os.path.join(target_dir, filename)

            # Track for summary
            files_by_watch[target_folder].append(filename)

            # Check if target already exists
            if os.path.exists(target_path):
                errors.append(f"Target exists: {target_path}")
                if verbose:
                    print(f"  ! SKIP (exists): {filename} -> {target_folder}/")
                continue

            # Create target folder if needed
            if not dry_run and not os.path.exists(target_dir):
                os.makedirs(target_dir)
                folders_created.add(target_folder)
            elif dry_run and not os.path.exists(target_dir):
                folders_created.add(target_folder)

            # Perform operation
            if verbose or dry_run:
                op_symbol = "📋" if copy else "📦"
                print(f"  {op_symbol} {operation}: {filename}")
                print(f"      FROM: {root}")
                print(f"      TO:   {target_dir}")

            if not dry_run:
                try:
                    if copy:
                        shutil.copy2(source_path, target_path)
                    else:
                        shutil.move(source_path, target_path)
                    files_processed += 1
                except Exception as e:
                    errors.append(f"Error processing {filename}: {str(e)}")
                    if verbose:
                        print(f"  ✗ ERROR: {str(e)}")
            else:
                files_processed += 1

    # Print summary
    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"Total images scanned: {total_images}")
    print(f"Back view images found: {back_views_found}")
    print(f"Files {operation.lower()}d: {files_processed}")
    print(f"New folders {'would be created' if dry_run else 'created'}: {len(folders_created)}")

    if errors:
        print(f"\nErrors encountered: {len(errors)}")
        for error in errors:
            print(f"  - {error}")

    if files_by_watch:
        print(f"\n{operation.title()}d files by watch:")
        for folder in sorted(files_by_watch.keys()):
            count = len(files_by_watch[folder])
            print(f"  {folder}: {count} image{'s' if count != 1 else ''}")

    print()
    if dry_run:
        print("⚠️  DRY RUN MODE - No files were actually moved")
        print("   Run without --dry-run to perform the operation")
    else:
        print("✓ Operation completed successfully!")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Separate back view watch images into dedicated folders.",
        epilog="""
Examples:
  # Preview changes without moving files
  python separate_back_views.py --dry-run

  # Move back view images to new folders
  python separate_back_views.py

  # Copy instead of move
  python separate_back_views.py --copy

  # Use custom images directory
  python separate_back_views.py --images-dir /path/to/downloaded_images

  # Verbose output with dry run
  python separate_back_views.py --dry-run --verbose
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--images-dir",
        type=str,
        default=None,
        help="Path to downloaded_images directory (default: ../downloaded_images relative to script)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without moving files (default: False)",
    )

    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy files instead of moving (default: False, will move)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed file operations (default: False)",
    )

    args = parser.parse_args()

    # Set default images directory if not specified
    if args.images_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.images_dir = os.path.join(script_dir, "..", "downloaded_images")

    # Normalize path
    args.images_dir = os.path.abspath(args.images_dir)

    # Process images
    process_images(args.images_dir, args.dry_run, args.copy, args.verbose)


if __name__ == "__main__":
    main()
