#!/usr/bin/env python3
"""Create CVAT tasks for watch annotation.

This is a helper script that creates properly configured CVAT tasks
with the correct label schema for watch landmark annotation.

Usage:
    python create_task.py --watch PATEK_nab_001
    python create_task.py --watch PATEK_nab_001 --with-annotations
    python create_task.py --all
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cvat.scripts.config import (
    CVAT_HOST, CVAT_USERNAME, CVAT_PASSWORD,
    IMAGES_DIR, ALIGNMENT_LABELS_DIR, KEYPOINT_ORDER, LABEL_NAME
)


def get_watch_folders() -> List[str]:
    """Get list of all watch folders."""
    if not IMAGES_DIR.exists():
        return []
    
    folders = []
    for d in IMAGES_DIR.iterdir():
        if d.is_dir() and not d.name.startswith('.'):
            folders.append(d.name)
    
    return sorted(folders)


def get_image_count(watch_id: str) -> int:
    """Get number of images in a watch folder."""
    watch_dir = IMAGES_DIR / watch_id
    if not watch_dir.exists():
        return 0
    return len(list(watch_dir.glob("*.jpg")))


def has_annotations(watch_id: str) -> bool:
    """Check if a watch has annotations."""
    json_path = ALIGNMENT_LABELS_DIR / f"{watch_id}.json"
    return json_path.exists()


def get_annotation_count(watch_id: str) -> int:
    """Get number of annotated images for a watch."""
    json_path = ALIGNMENT_LABELS_DIR / f"{watch_id}.json"
    if not json_path.exists():
        return 0
    
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        return len(data)
    except Exception:
        return 0


def print_watch_status(watch_ids: Optional[List[str]] = None):
    """Print status of watch folders."""
    if watch_ids is None:
        watch_ids = get_watch_folders()
    
    print(f"\n{'Watch ID':<20} {'Images':>8} {'Annotated':>10} {'Status':<15}")
    print("-" * 60)
    
    total_images = 0
    total_annotated = 0
    
    for watch_id in watch_ids:
        image_count = get_image_count(watch_id)
        annotation_count = get_annotation_count(watch_id)
        
        total_images += image_count
        total_annotated += annotation_count
        
        if annotation_count == 0:
            status = "Not started"
        elif annotation_count < image_count:
            status = "In progress"
        else:
            status = "Complete ✓"
        
        print(f"{watch_id:<20} {image_count:>8} {annotation_count:>10} {status:<15}")
    
    print("-" * 60)
    print(f"{'TOTAL':<20} {total_images:>8} {total_annotated:>10}")
    
    if total_images > 0:
        coverage = total_annotated / total_images * 100
        print(f"\nOverall coverage: {coverage:.1f}%")


def generate_task_instructions():
    """Generate instructions for creating tasks in CVAT."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                 CVAT Task Creation Guide                          ║
╚══════════════════════════════════════════════════════════════════╝

STEP 1: Start CVAT
─────────────────────────────────────────────────────────────────────
  cd cvat
  ./run_cvat_local.sh start

STEP 2: Create Superuser (first time only)
─────────────────────────────────────────────────────────────────────
  ./run_cvat_local.sh create-superuser

STEP 3: Access CVAT UI
─────────────────────────────────────────────────────────────────────
  Open: http://localhost:8080
  Login with your superuser credentials

STEP 4: Create Project
─────────────────────────────────────────────────────────────────────
  1. Click "Projects" → "Create new project"
  2. Name: "Watch Annotations"
  3. Add labels:
     - Click "Add label"
     - Name: "watch_landmarks"
     - Type: Skeleton
     - Add sublabels: top, bottom, left, right, center
     - Add attributes:
       * quality (select): bad, partial, full
       * view_type (select): face, tiltface
  4. Click "Submit"

STEP 5: Create Tasks (for each watch folder)
─────────────────────────────────────────────────────────────────────
  1. Click "Tasks" → "Create new task"
  2. Name: Use watch ID (e.g., "PATEK_nab_001")
  3. Project: Select "Watch Annotations"
  4. Files:
     - Click "Connected file share"
     - Navigate to the watch folder
     - Select all images
  5. Click "Submit & Open"

STEP 6: Import Existing Annotations (optional)
─────────────────────────────────────────────────────────────────────
  If you have existing annotations:
  
  # First convert to CVAT format
  python cvat/scripts/convert_internal_to_cvat.py --all --output ./cvat_exports
  
  Then in CVAT:
  1. Open the task
  2. Click "Actions" → "Upload annotations"
  3. Format: "CVAT for images 1.1"
  4. Select the corresponding XML file

═══════════════════════════════════════════════════════════════════

ANNOTATION WORKFLOW
─────────────────────────────────────────────────────────────────────
  1. Open a task job
  2. Select the skeleton tool
  3. For each image, click 5 points in order:
     - TOP (12 o'clock)
     - BOTTOM (6 o'clock)
     - LEFT (9 o'clock)
     - RIGHT (3 o'clock)
     - CENTER (dial center)
  4. Use N/P keys for next/previous image
  5. Save frequently (Ctrl+S)

EXPORTING ANNOTATIONS
─────────────────────────────────────────────────────────────────────
  Via UI:
    1. Open task → Actions → Export annotations
    2. Format: "CVAT for images 1.1"
    3. Download XML file
  
  Via API:
    python cvat/scripts/export_from_cvat.py --project "Watch Annotations" --output ./exports/
  
  Convert back to internal format:
    python cvat/scripts/convert_cvat_to_internal.py --input ./exports/ --output ./alignment_labels/
""")


def main():
    parser = argparse.ArgumentParser(
        description="Create CVAT tasks for watch annotation"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all watch folders with status"
    )
    parser.add_argument(
        "--guide",
        action="store_true",
        help="Show task creation guide"
    )
    parser.add_argument(
        "--watch",
        type=str,
        help="Show status for specific watch"
    )
    
    args = parser.parse_args()
    
    if args.guide:
        generate_task_instructions()
        return
    
    if args.list:
        print_watch_status()
        return
    
    if args.watch:
        print_watch_status([args.watch])
        return
    
    # Default: show guide and status
    generate_task_instructions()
    print("\n\nCURRENT STATUS:")
    print_watch_status()


if __name__ == "__main__":
    main()
