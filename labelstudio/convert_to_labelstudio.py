#!/usr/bin/env python3
"""
Convert internal annotation format to Label Studio format.

This script converts the existing annotation JSON files from the internal format
to Label Studio's task format with pre-annotations (predictions).

Usage:
    python convert_to_labelstudio.py --input-dir ../alignment_labels --output tasks.json
    python convert_to_labelstudio.py --input-dir ../alignment_labels --output tasks.json --image-base-url /data/local-files/?d=
"""

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_result_id() -> str:
    """Generate a unique result ID for Label Studio annotations."""
    return str(uuid.uuid4())[:8]


def convert_crop_bbox_to_roi(
    crop_bbox: List[int],
    original_image_size: List[int],
) -> Optional[Dict[str, Any]]:
    """
    Convert internal crop_bbox to Label Studio rectangle format.

    Args:
        crop_bbox: [x1, y1, x2, y2] in pixels
        original_image_size: [width, height] of original image

    Returns:
        Label Studio rectangle annotation dict, or None if invalid
    """
    if not crop_bbox or len(crop_bbox) != 4:
        return None

    x1, y1, x2, y2 = crop_bbox
    orig_width, orig_height = original_image_size

    # Convert to percentages (0-100)
    x_pct = (x1 / orig_width) * 100
    y_pct = (y1 / orig_height) * 100
    width_pct = ((x2 - x1) / orig_width) * 100
    height_pct = ((y2 - y1) / orig_height) * 100

    # Validate bounds
    if width_pct <= 0 or height_pct <= 0:
        return None

    return {
        "id": generate_result_id(),
        "from_name": "crop_roi",
        "to_name": "image",
        "type": "rectanglelabels",
        "origin": "manual",
        "value": {
            "x": x_pct,
            "y": y_pct,
            "width": width_pct,
            "height": height_pct,
            "rectanglelabels": ["Crop ROI"],
        },
    }


def convert_keypoint(
    keypoint_name: str,
    coords: List[float],
) -> Dict[str, Any]:
    """
    Convert internal keypoint to Label Studio keypoint format.

    Args:
        keypoint_name: Name of the keypoint (top, bottom, left, right, center)
        coords: [x, y] normalized coordinates (0-1)

    Returns:
        Label Studio keypoint annotation dict
    """
    # Convert normalized (0-1) to percentage (0-100)
    x_pct = coords[0] * 100
    y_pct = coords[1] * 100

    # Label Studio expects capitalized label names
    label = keypoint_name.capitalize()

    return {
        "id": generate_result_id(),
        "from_name": "keypoints",
        "to_name": "image",
        "type": "keypointlabels",
        "origin": "manual",
        "value": {
            "x": x_pct,
            "y": y_pct,
            "width": 0.75,  # Default keypoint display width
            "keypointlabels": [label],
        },
    }


def convert_annotation_to_labelstudio(
    image_key: str,
    annotation: Dict[str, Any],
    image_base_url: str,
) -> Dict[str, Any]:
    """
    Convert a single internal annotation to Label Studio task format.

    Args:
        image_key: The image identifier (e.g., "PATEK_nab_001_01")
        annotation: The internal annotation dict
        image_base_url: Base URL/path for images

    Returns:
        Label Studio task dict with predictions
    """
    # Extract watch folder from image key (e.g., "PATEK_nab_001" from "PATEK_nab_001_01")
    parts = image_key.rsplit("_", 1)
    watch_folder = parts[0] if len(parts) > 1 else image_key

    # Build image path
    full_image_name = annotation.get("full_image_name", image_key)
    image_path = f"{watch_folder}/{full_image_name}.jpg"
    image_url = f"{image_base_url}{image_path}"

    # Build predictions/results
    results = []

    # Add crop ROI if available
    crop_bbox = annotation.get("crop_bbox")
    original_size = annotation.get("original_image_size")
    if crop_bbox and original_size:
        roi = convert_crop_bbox_to_roi(crop_bbox, original_size)
        if roi:
            results.append(roi)

    # Add keypoints
    coords_norm = annotation.get("coords_norm", {})
    for keypoint_name, coords in coords_norm.items():
        if coords and len(coords) == 2:
            results.append(convert_keypoint(keypoint_name, coords))

    task = {
        "data": {
            "image": image_url,
            "image_key": image_key,
            "watch_folder": watch_folder,
        },
        "predictions": [
            {
                "result": results,
            }
        ],
    }

    return task


def load_internal_annotations(input_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load all internal annotation files from a directory.

    Args:
        input_dir: Path to directory containing annotation JSON files

    Returns:
        Dict mapping image_key to annotation data
    """
    all_annotations = {}

    for json_file in sorted(input_dir.glob("*.json")):
        if json_file.name == ".gitkeep":
            continue

        with open(json_file) as f:
            data = json.load(f)

        # Each file contains multiple image annotations
        for image_key, annotation in data.items():
            all_annotations[image_key] = annotation

    return all_annotations


def convert_all_annotations(
    input_dir: Path,
    image_base_url: str,
) -> List[Dict[str, Any]]:
    """
    Convert all internal annotations to Label Studio format.

    Args:
        input_dir: Path to directory containing annotation JSON files
        image_base_url: Base URL/path for images

    Returns:
        List of Label Studio task dicts
    """
    annotations = load_internal_annotations(input_dir)
    tasks = []

    for image_key, annotation in annotations.items():
        task = convert_annotation_to_labelstudio(
            image_key,
            annotation,
            image_base_url,
        )
        tasks.append(task)

    return tasks


def main():
    parser = argparse.ArgumentParser(
        description="Convert internal annotations to Label Studio format"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("../alignment_labels"),
        help="Directory containing internal annotation JSON files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tasks.json"),
        help="Output file for Label Studio tasks",
    )
    parser.add_argument(
        "--image-base-url",
        type=str,
        default="/data/local-files/?d=",
        help="Base URL/path for images in Label Studio",
    )

    args = parser.parse_args()

    # Resolve paths
    input_dir = args.input_dir.resolve()
    output_file = args.output

    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        return 1

    print(f"Loading annotations from: {input_dir}")
    tasks = convert_all_annotations(input_dir, args.image_base_url)

    print(f"Converted {len(tasks)} tasks")

    # Write output
    with open(output_file, "w") as f:
        json.dump(tasks, f, indent=2)

    print(f"Wrote Label Studio tasks to: {output_file}")
    return 0


if __name__ == "__main__":
    exit(main())
