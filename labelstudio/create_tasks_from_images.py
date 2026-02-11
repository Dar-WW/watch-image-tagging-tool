#!/usr/bin/env python3
"""
Create Label Studio tasks from images without predictions.

This script scans the downloaded_images directory and creates Label Studio
tasks for images that don't have existing annotations. Useful for annotating
new images from scratch.

Usage:
    # Create tasks for all unannotated images
    python create_tasks_from_images.py --output new_tasks.json

    # Create tasks for specific watch model
    python create_tasks_from_images.py --watch-id CARTIER_sant_001 --output tasks.json

    # Only face views
    python create_tasks_from_images.py --view-type face --output tasks.json

    # Include images that already have annotations
    python create_tasks_from_images.py --include-annotated --output tasks.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.filename_parser import get_image_id, parse_filename


def load_existing_image_ids(annotations_dirs: List[Path]) -> Set[str]:
    """
    Load image IDs from existing annotation files.

    Args:
        annotations_dirs: List of directories containing annotation JSON files

    Returns:
        Set of image IDs that already have annotations
    """
    existing_ids = set()

    for anno_dir in annotations_dirs:
        if not anno_dir.exists():
            continue

        for json_file in anno_dir.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                existing_ids.update(data.keys())
            except Exception as e:
                print(f"Warning: Failed to read {json_file}: {e}", file=sys.stderr)

    return existing_ids


def scan_images(
    images_dir: Path,
    view_type_filter: Optional[str] = None,
    watch_id_filter: Optional[str] = None,
    skip_existing: bool = True,
    existing_ids: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Scan images directory and collect image metadata.

    Args:
        images_dir: Directory containing watch images
        view_type_filter: Only include this view type (face/tiltface/back)
        watch_id_filter: Only include this watch ID
        skip_existing: Skip images already in existing_ids
        existing_ids: Set of image IDs to skip (if skip_existing=True)

    Returns:
        List of image metadata dicts
    """
    if not images_dir.exists():
        print(f"Error: Images directory not found: {images_dir}", file=sys.stderr)
        return []

    if existing_ids is None:
        existing_ids = set()

    images = []

    for watch_dir in sorted(images_dir.iterdir()):
        if not watch_dir.is_dir():
            continue

        watch_id = watch_dir.name

        # Apply watch_id filter
        if watch_id_filter and watch_id != watch_id_filter:
            continue

        for image_file in sorted(watch_dir.glob("*.jpg")):
            try:
                # Parse filename
                metadata = parse_filename(image_file.name)
                if not metadata:
                    continue

                # Apply view type filter
                if view_type_filter and metadata.view_type != view_type_filter:
                    continue

                # Get quality-agnostic image ID
                image_id = get_image_id(image_file.name)

                # Skip if already annotated
                if skip_existing and image_id in existing_ids:
                    continue

                images.append({
                    "filename": image_file.name,
                    "image_id": image_id,
                    "watch_id": watch_id,
                    "view_type": metadata.view_type,
                    "quality": metadata.quality,
                })

            except Exception as e:
                print(f"Warning: Failed to process {image_file.name}: {e}", file=sys.stderr)

    return images


def create_labelstudio_task(
    image_metadata: Dict[str, Any],
    image_base_url: str,
) -> Dict[str, Any]:
    """
    Create a Label Studio task from image metadata without predictions.

    Args:
        image_metadata: Image metadata dict with filename, image_id, watch_id
        image_base_url: Base URL/path for images in Label Studio

    Returns:
        Label Studio task dict without predictions
    """
    filename = image_metadata["filename"]
    image_id = image_metadata["image_id"]
    watch_id = image_metadata["watch_id"]

    # Build image path
    # Note: Images are mounted at /label-studio/media/images/ in Docker
    image_path = f"images/{watch_id}/{filename}"
    image_url = f"{image_base_url}{image_path}"

    task = {
        "data": {
            "image": image_url,
            "image_key": image_id,
            "watch_folder": watch_id,
            "view_type": image_metadata.get("view_type"),
            "quality": image_metadata.get("quality"),
        }
    }

    return task


def main():
    parser = argparse.ArgumentParser(
        description="Create Label Studio tasks from images without predictions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create tasks for all unannotated images
  python create_tasks_from_images.py --output new_tasks.json

  # Create tasks for specific watch model
  python create_tasks_from_images.py --watch-id CARTIER_sant_001 --output tasks.json

  # Only face views, minimum quality 2
  python create_tasks_from_images.py --view-type face --min-quality 2 --output tasks.json

  # Include images that already have annotations
  python create_tasks_from_images.py --include-annotated --output tasks.json
        """
    )

    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path("../../FPJ-WatchId-POC/data/aligned/nab/downloaded_images"),
        help="Directory containing watch images (default: ../downloaded_images)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output file for Label Studio tasks",
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        action="append",
        help="Directory with existing annotations to skip (can specify multiple times)",
    )
    parser.add_argument(
        "--image-base-url",
        type=str,
        default="/data/local-files/?d=",
        help="Base URL/path for images in Label Studio (default: /data/local-files/?d=)",
    )
    parser.add_argument(
        "--view-type",
        type=str,
        choices=["face", "tiltface", "back"],
        help="Only include images of this view type",
    )
    parser.add_argument(
        "--watch-id",
        type=str,
        help="Only include images from this watch model",
    )
    parser.add_argument(
        "--min-quality",
        type=int,
        choices=[1, 2, 3],
        help="Minimum image quality (1-3)",
    )
    parser.add_argument(
        "--include-annotated",
        action="store_true",
        help="Include images that already have annotations",
    )

    args = parser.parse_args()

    # Resolve paths
    images_dir = args.images_dir.resolve()

    if not images_dir.exists():
        print(f"Error: Images directory does not exist: {images_dir}", file=sys.stderr)
        return 1

    # Load existing annotations
    existing_ids = set()
    if not args.include_annotated:
        # Default annotation directories to check
        annotation_dirs = []
        if args.annotations_dir:
            annotation_dirs.extend(args.annotations_dir)
        else:
            # Check both human and predicted annotations
            annotation_dirs.extend([
                Path(__file__).parent.parent / "alignment_labels",
                Path(__file__).parent.parent / "alignment_labels_predicted",
            ])

        existing_ids = load_existing_image_ids(annotation_dirs)
        print(f"Found {len(existing_ids)} already annotated images")

    # Scan images
    print(f"Scanning images in: {images_dir}")
    images = scan_images(
        images_dir,
        view_type_filter=args.view_type,
        watch_id_filter=args.watch_id,
        skip_existing=not args.include_annotated,
        existing_ids=existing_ids,
    )

    # Apply quality filter
    if args.min_quality:
        images = [img for img in images if img.get("quality", 0) >= args.min_quality]

    print(f"Found {len(images)} images to create tasks for")

    if not images:
        print("No images to process")
        return 0

    # Create tasks
    tasks = []
    for image_metadata in images:
        task = create_labelstudio_task(image_metadata, args.image_base_url)
        tasks.append(task)

    # Write output
    with open(args.output, "w") as f:
        json.dump(tasks, f, indent=2)

    print(f"Created {len(tasks)} tasks")
    print(f"Wrote Label Studio tasks to: {args.output}")

    # Print summary
    print("\nSummary by view type:")
    view_counts = {}
    for img in images:
        view_type = img.get("view_type", "unknown")
        view_counts[view_type] = view_counts.get(view_type, 0) + 1

    for view_type, count in sorted(view_counts.items()):
        print(f"  {view_type}: {count}")

    return 0


if __name__ == "__main__":
    exit(main())
