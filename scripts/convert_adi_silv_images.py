#!/usr/bin/env python3
"""
Convert ADI_silv watch images from HEIC to JPG and rename to proper format.
Maps folder numbers to sequential watch numbers and images to sequential view numbers.
"""

import os
import subprocess
from pathlib import Path
from collections import defaultdict

# Configuration
BRAND = "ADI"
MODEL = "silv"
VIEW_TYPE = "face"
QUALITY = "q3"
BASE_DIR = Path(__file__).parent.parent / "downloaded_images"

# Folder number to watch number mapping
# Folders 2-12 (missing 1, 6) → watches 001-010
FOLDER_MAPPING = {
    2: 1,
    3: 2,
    4: 3,
    5: 4,
    7: 5,
    8: 6,
    9: 7,
    10: 8,
    11: 9,
    12: 10,
}


def convert_heic_to_jpg(heic_path: Path, jpg_path: Path) -> bool:
    """
    Convert HEIC image to JPG using sips (macOS built-in tool).

    Args:
        heic_path: Path to HEIC file
        jpg_path: Path for output JPG file

    Returns:
        True if successful, False otherwise
    """
    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(heic_path), "--out", str(jpg_path)],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {heic_path}: {e}")
        return False


def process_folder(folder_num: int, watch_num: int) -> bool:
    """
    Process a single folder: convert HEIC to JPG and rename.

    Args:
        folder_num: Current folder number
        watch_num: Target watch number

    Returns:
        True if successful, False otherwise
    """
    source_folder = BASE_DIR / str(folder_num)
    if not source_folder.exists():
        print(f"Folder {folder_num} does not exist, skipping")
        return False

    # Get all HEIC files sorted by name
    heic_files = sorted(source_folder.glob("*.HEIC"))
    if not heic_files:
        print(f"No HEIC files found in folder {folder_num}, skipping")
        return False

    print(f"\nProcessing folder {folder_num} → watch {watch_num:03d} ({len(heic_files)} images)")

    # Create target folder name
    watch_id = f"{BRAND}_{MODEL}_{watch_num:03d}"
    target_folder = BASE_DIR / watch_id

    # Create target folder if it doesn't exist
    target_folder.mkdir(exist_ok=True)

    # Process each image
    success_count = 0
    for view_num, heic_file in enumerate(heic_files, start=1):
        # Generate target filename
        target_filename = f"{watch_id}_{view_num:02d}_{VIEW_TYPE}_{QUALITY}.jpg"
        target_path = target_folder / target_filename

        # Convert HEIC to JPG
        print(f"  {heic_file.name} → {target_filename}")
        if convert_heic_to_jpg(heic_file, target_path):
            success_count += 1
        else:
            print(f"  ✗ Failed to convert {heic_file.name}")

    print(f"  ✓ Converted {success_count}/{len(heic_files)} images")

    # Remove old folder if all conversions successful
    if success_count == len(heic_files):
        print(f"  Removing old folder {folder_num}")
        for heic_file in heic_files:
            heic_file.unlink()
        source_folder.rmdir()

    return success_count == len(heic_files)


def main():
    """Main conversion process."""
    print(f"Converting ADI_silv images in {BASE_DIR}")
    print(f"Format: {BRAND}_{MODEL}_XXX_YY_{VIEW_TYPE}_{QUALITY}.jpg\n")

    total_folders = len(FOLDER_MAPPING)
    successful = 0

    for folder_num, watch_num in sorted(FOLDER_MAPPING.items()):
        if process_folder(folder_num, watch_num):
            successful += 1

    print(f"\n{'='*60}")
    print(f"Conversion complete: {successful}/{total_folders} folders processed successfully")
    print(f"{'='*60}")

    # List final structure
    print("\nFinal folder structure:")
    adi_folders = sorted(BASE_DIR.glob(f"{BRAND}_{MODEL}_*"))
    for folder in adi_folders:
        jpg_count = len(list(folder.glob("*.jpg")))
        print(f"  {folder.name}: {jpg_count} images")


if __name__ == "__main__":
    main()
