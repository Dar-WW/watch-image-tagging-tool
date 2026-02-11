#!/usr/bin/env python3
"""
Rename EMBOSS_premopn watch images to proper format.
Maps folder numbers to sequential watch numbers and images to sequential view numbers.
Handles both JPG and HEIC files (converts HEIC to JPG).
"""

import shutil
import subprocess
from pathlib import Path

# Configuration
BRAND = "EMBOSS"
MODEL = "premopn"
VIEW_TYPE = "face"
QUALITY = "q3"
BASE_DIR = Path(__file__).parent.parent / "downloaded_images"

# Folder numbers 1-12 map directly to watch numbers 001-012
FOLDER_MAPPING = {i: i for i in range(1, 13)}


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
    Process a single folder: convert HEIC and rename JPG files.

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

    # Get all image files (both JPG and HEIC) sorted by name
    jpg_files = sorted(source_folder.glob("*.JPG")) + sorted(source_folder.glob("*.jpg"))
    heic_files = sorted(source_folder.glob("*.HEIC")) + sorted(source_folder.glob("*.heic"))
    all_files = sorted(jpg_files + heic_files, key=lambda x: x.name)

    if not all_files:
        print(f"No image files found in folder {folder_num}, skipping")
        return False

    print(f"\nProcessing folder {folder_num} → watch {watch_num:03d} ({len(all_files)} images: {len(jpg_files)} JPG, {len(heic_files)} HEIC)")

    # Create target folder name
    watch_id = f"{BRAND}_{MODEL}_{watch_num:03d}"
    target_folder = BASE_DIR / watch_id

    # Create target folder if it doesn't exist
    target_folder.mkdir(exist_ok=True)

    # Process each image
    success_count = 0
    for view_num, image_file in enumerate(all_files, start=1):
        # Generate target filename
        target_filename = f"{watch_id}_{view_num:02d}_{VIEW_TYPE}_{QUALITY}.jpg"
        target_path = target_folder / target_filename

        # Handle based on file type
        if image_file.suffix.upper() == ".HEIC":
            # Convert HEIC to JPG
            print(f"  {image_file.name} → {target_filename} (converting)")
            if convert_heic_to_jpg(image_file, target_path):
                success_count += 1
            else:
                print(f"  ✗ Failed to convert {image_file.name}")
        else:
            # Copy JPG file with new name
            print(f"  {image_file.name} → {target_filename}")
            try:
                shutil.copy2(image_file, target_path)
                success_count += 1
            except Exception as e:
                print(f"  ✗ Failed to copy {image_file.name}: {e}")

    print(f"  ✓ Processed {success_count}/{len(all_files)} images")

    # Remove old folder if all conversions/copies successful
    if success_count == len(all_files):
        print(f"  Removing old folder {folder_num}")
        for image_file in all_files:
            image_file.unlink()
        source_folder.rmdir()

    return success_count == len(all_files)


def main():
    """Main conversion process."""
    print(f"Converting EMBOSS_premopn images in {BASE_DIR}")
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
    emboss_folders = sorted(BASE_DIR.glob(f"{BRAND}_{MODEL}_*"))
    for folder in emboss_folders:
        jpg_count = len(list(folder.glob("*.jpg")))
        print(f"  {folder.name}: {jpg_count} images")


if __name__ == "__main__":
    main()
