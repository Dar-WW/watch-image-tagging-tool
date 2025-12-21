#!/usr/bin/env python3
"""
Export Label Studio annotations back to internal format.

This script converts Label Studio's exported JSON annotations back to
the internal annotation format used by the project.

Usage:
    python export_from_labelstudio.py --input export.json --output-dir ../alignment_labels
    python export_from_labelstudio.py --input export.json --output-dir ../alignment_labels --merge
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def parse_rectangle_roi(
    result: Dict[str, Any],
    original_width: int,
    original_height: int,
) -> Optional[List[int]]:
    """
    Parse Label Studio rectangle ROI to internal crop_bbox format.

    Args:
        result: Label Studio result dict for rectangle
        original_width: Original image width in pixels
        original_height: Original image height in pixels

    Returns:
        crop_bbox as [x1, y1, x2, y2] in pixels, or None if invalid
    """
    value = result.get("value", {})

    # Label Studio uses percentages (0-100)
    x_pct = value.get("x", 0)
    y_pct = value.get("y", 0)
    width_pct = value.get("width", 0)
    height_pct = value.get("height", 0)

    # Convert to pixels
    x1 = int((x_pct / 100) * original_width)
    y1 = int((y_pct / 100) * original_height)
    x2 = int(((x_pct + width_pct) / 100) * original_width)
    y2 = int(((y_pct + height_pct) / 100) * original_height)

    return [x1, y1, x2, y2]


def parse_keypoint(
    result: Dict[str, Any],
) -> Optional[Tuple[str, List[float]]]:
    """
    Parse Label Studio keypoint to internal format.

    Args:
        result: Label Studio result dict for keypoint

    Returns:
        Tuple of (keypoint_name, [x, y]) with normalized coords, or None if invalid
    """
    value = result.get("value", {})

    # Get label name
    labels = value.get("keypointlabels", [])
    if not labels:
        return None

    label = labels[0].lower()  # e.g., "Top" -> "top"

    # Label Studio uses percentages (0-100), convert to normalized (0-1)
    x_norm = value.get("x", 0) / 100
    y_norm = value.get("y", 0) / 100

    return (label, [x_norm, y_norm])


def extract_image_key_from_task(task: Dict[str, Any]) -> Optional[str]:
    """
    Extract image key from Label Studio task data.

    Args:
        task: Label Studio task dict

    Returns:
        Image key string, or None if not found
    """
    data = task.get("data", {})

    # Try explicit image_key first
    if "image_key" in data:
        return data["image_key"]

    # Try to extract from image path
    image_path = data.get("image", "")

    # Extract filename from path (e.g., ".../PATEK_nab_001/PATEK_nab_001_01_face_q3.jpg")
    match = re.search(r"(PATEK_\w+_\d+_\d+)", image_path)
    if match:
        return match.group(1)

    return None


def extract_watch_folder(image_key: str) -> str:
    """
    Extract watch folder from image key.

    Args:
        image_key: e.g., "PATEK_nab_001_01"

    Returns:
        Watch folder, e.g., "PATEK_nab_001"
    """
    parts = image_key.rsplit("_", 1)
    return parts[0] if len(parts) > 1 else image_key


def convert_task_to_internal(
    task: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Convert a Label Studio task/annotation to internal format.

    Args:
        task: Label Studio task dict with annotations

    Returns:
        Internal annotation dict, or None if invalid
    """
    image_key = extract_image_key_from_task(task)
    if not image_key:
        return None

    # Get annotations (could be in 'annotations' or 'completions' for older exports)
    annotations = task.get("annotations", []) or task.get("completions", [])

    if not annotations:
        # No annotations yet, skip
        return None

    # Use the most recent annotation
    latest_annotation = annotations[-1]
    results = latest_annotation.get("result", [])

    if not results:
        return None

    # Initialize internal format
    internal = {
        "coords_norm": {},
    }

    # Get original image dimensions from result (if available)
    original_width = None
    original_height = None

    for result in results:
        if "original_width" in result:
            original_width = result["original_width"]
        if "original_height" in result:
            original_height = result["original_height"]

    # Parse results
    for result in results:
        result_type = result.get("type", "")

        if result_type == "rectanglelabels":
            # Check if this is a Crop ROI
            labels = result.get("value", {}).get("rectanglelabels", [])
            if "Crop ROI" in labels and original_width and original_height:
                crop_bbox = parse_rectangle_roi(result, original_width, original_height)
                if crop_bbox:
                    internal["crop_bbox"] = crop_bbox
                    internal["original_image_size"] = [original_width, original_height]

        elif result_type == "keypointlabels":
            keypoint = parse_keypoint(result)
            if keypoint:
                name, coords = keypoint
                internal["coords_norm"][name] = coords

    # Extract full_image_name from task data if available
    data = task.get("data", {})
    image_path = data.get("image", "")
    match = re.search(r"([^/]+)\.jpg", image_path, re.IGNORECASE)
    if match:
        internal["full_image_name"] = match.group(1)

    return {image_key: internal}


def convert_labelstudio_export(
    export_data: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Convert Label Studio export to internal format, grouped by watch folder.

    Args:
        export_data: List of Label Studio task dicts

    Returns:
        Dict mapping watch_folder -> {image_key -> annotation}
    """
    grouped = defaultdict(dict)

    for task in export_data:
        result = convert_task_to_internal(task)
        if result:
            for image_key, annotation in result.items():
                watch_folder = extract_watch_folder(image_key)
                grouped[watch_folder][image_key] = annotation

    return dict(grouped)


def load_existing_annotations(output_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load existing internal annotation files.

    Args:
        output_dir: Directory containing existing annotation files

    Returns:
        Dict mapping watch_folder -> {image_key -> annotation}
    """
    existing = {}

    for json_file in output_dir.glob("*.json"):
        if json_file.name == ".gitkeep":
            continue

        watch_folder = json_file.stem  # e.g., "PATEK_nab_001"

        with open(json_file) as f:
            existing[watch_folder] = json.load(f)

    return existing


def merge_annotations(
    existing: Dict[str, Dict[str, Any]],
    new: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Merge new annotations into existing ones.

    New annotations take precedence over existing ones.

    Args:
        existing: Existing annotations by watch_folder
        new: New annotations by watch_folder

    Returns:
        Merged annotations
    """
    merged = dict(existing)

    for watch_folder, annotations in new.items():
        if watch_folder not in merged:
            merged[watch_folder] = {}

        merged[watch_folder].update(annotations)

    return merged


def save_annotations(
    annotations: Dict[str, Dict[str, Any]],
    output_dir: Path,
) -> None:
    """
    Save annotations to individual JSON files per watch folder.

    Args:
        annotations: Dict mapping watch_folder -> {image_key -> annotation}
        output_dir: Directory to write annotation files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for watch_folder, data in annotations.items():
        output_file = output_dir / f"{watch_folder}.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Wrote: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Export Label Studio annotations to internal format"
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Label Studio export JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("../alignment_labels"),
        help="Output directory for internal annotation files",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge with existing annotations instead of overwriting",
    )

    args = parser.parse_args()

    input_file = args.input
    output_dir = args.output_dir.resolve()

    if not input_file.exists():
        print(f"Error: Input file does not exist: {input_file}")
        return 1

    # Load Label Studio export
    print(f"Loading Label Studio export from: {input_file}")
    with open(input_file) as f:
        export_data = json.load(f)

    # Handle both list and single task formats
    if isinstance(export_data, dict):
        export_data = [export_data]

    # Convert to internal format
    new_annotations = convert_labelstudio_export(export_data)
    print(f"Converted {sum(len(v) for v in new_annotations.values())} annotations")

    # Merge with existing if requested
    if args.merge and output_dir.exists():
        print("Loading existing annotations for merge...")
        existing = load_existing_annotations(output_dir)
        annotations = merge_annotations(existing, new_annotations)
    else:
        annotations = new_annotations

    # Save
    save_annotations(annotations, output_dir)

    print("Done!")
    return 0


if __name__ == "__main__":
    exit(main())
