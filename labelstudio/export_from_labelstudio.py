#!/usr/bin/env python3
"""
Export Label Studio annotations back to internal format.

This script converts Label Studio's exported JSON annotations back to
the internal annotation format used by the project.

When using --delete-discarded-images flag, this script will also:
- Delete images marked as discarded in Label Studio
- Delete entire watch directories with fewer than 2 face/tiltface images

Usage:
    python export_from_labelstudio.py --input export.json --output-dir ../alignment_labels
    python export_from_labelstudio.py --input export.json --output-dir ../alignment_labels --merge
    python export_from_labelstudio.py --input export.json --output-dir ../alignment_labels --delete-discarded-images
"""

import argparse
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from typing import Any, Dict, List, Optional, Tuple


# --- Rotation correction utilities ---
def parse_rotation_correction(results: List[Dict[str, Any]]) -> str:
    """Extract rotation correction choice from Label Studio results.

    Expected labeling config:
      <Choices name="rotation_correction" ...>
        <Choice value="0" />
        <Choice value="90_cw" />
        <Choice value="180" />
        <Choice value="270_cw" />
      </Choices>

    Returns:
        One of: "0", "90_cw", "180", "270_cw".
        Defaults to "0" if not present.
    """
    for r in results:
        if r.get("type") != "choices":
            continue
        # Depending on LS export, this can appear as from_name or name
        if r.get("from_name") != "rotation_correction" and r.get("name") != "rotation_correction":
            continue
        value = r.get("value", {})
        choices = value.get("choices", [])
        if not choices:
            return "0"
        # Single choice expected
        return str(choices[0])
    return "0"


def parse_discard_image(results: List[Dict[str, Any]]) -> bool:
    """Return True if the annotator marked this task/image as discarded.

    Expected labeling config (recommended):
      <Choices name="discard_image" choice="multiple" required="false">
        <Choice value="discard" />
      </Choices>

    We treat any selection as discard.
    """
    for r in results:
        if r.get("type") != "choices":
            continue
        if r.get("from_name") != "discard_image" and r.get("name") != "discard_image":
            continue
        value = r.get("value", {})
        choices = value.get("choices", [])
        return bool(choices)
    return False


def remap_keypoint_labels(rotation: str) -> Dict[str, str]:
    """Return a mapping old_label -> new_label for 4-way compass labels.

    This implements a *label remap* (keys change, coordinates stay the same).

    Convention:
      - rotation == "90_cw": rotate labels clockwise (top->right->bottom->left)
      - rotation == "180": rotate labels 180 degrees
      - rotation == "270_cw": rotate labels clockwise 270 degrees (equivalent to 90 CCW: top->left->bottom->right)

    "center" is left unchanged.
    """
    if rotation == "90_cw":
        return {
            # NOTE: In practice we interpret the selected value as "image is rotated CW",
            # so we remap labels in the opposite direction to correct them.
            "top": "left",
            "left": "bottom",
            "bottom": "right",
            "right": "top",
            "center": "center",
        }
    if rotation == "180":
        return {
            "top": "bottom",
            "bottom": "top",
            "left": "right",
            "right": "left",
            "center": "center",
        }
    if rotation == "270_cw":
        return {
            "top": "right",
            "right": "bottom",
            "bottom": "left",
            "left": "top",
            "center": "center",
        }

    # "0" or unknown
    return {
        "top": "top",
        "bottom": "bottom",
        "left": "left",
        "right": "right",
        "center": "center",
    }


def apply_rotation_correction_to_coords(
    coords_norm: Dict[str, List[float]],
    rotation: str,
    original_width: Optional[int],
    original_height: Optional[int],
) -> Dict[str, List[float]]:
    """Apply rotation correction by remapping labels (keys) while keeping coords.

    Note: `original_width` / `original_height` are intentionally unused in this
    mode; they remain in the signature to avoid touching call sites.
    """
    if rotation in ("0", "", None):
        return coords_norm

    mapping = remap_keypoint_labels(rotation)

    corrected: Dict[str, List[float]] = {}
    for old_label, xy in coords_norm.items():
        if not xy or len(xy) != 2:
            continue
        new_label = mapping.get(old_label, old_label)
        corrected[new_label] = xy

    return corrected


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

    # Extract filename from path (e.g., ".../BRAND_model_001/BRAND_model_001_01_face_q3.jpg")
    # Pattern: BRAND_model_number_view (e.g., PATEK_nab_001_01, ROLEX_sub_042_03)
    match = re.search(r"([A-Z]+_[a-z]+_\d+_\d+)", image_path)
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

    rotation_correction = parse_rotation_correction(results)
    discard_image = parse_discard_image(results)

    if discard_image:
        internal = {"discard": True}
        # Preserve traceability fields when possible
        if original_width and original_height:
            internal["image_size"] = [original_width, original_height]
        # Extract full_image_name from task data if available
        data = task.get("data", {})
        image_path = data.get("image", "")
        match = re.search(r"([^/]+)\.jpg", image_path, re.IGNORECASE)
        if match:
            internal["full_image_name"] = match.group(1)
        return {image_key: internal}

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
                    internal["image_size"] = [original_width, original_height]

        elif result_type == "keypointlabels":
            keypoint = parse_keypoint(result)
            if keypoint:
                name, coords = keypoint
                internal["coords_norm"][name] = coords

    # Apply optional rotation correction to keypoints
    if internal.get("coords_norm"):
        internal["coords_norm"] = apply_rotation_correction_to_coords(
            internal["coords_norm"],
            rotation_correction,
            original_width,
            original_height,
        )

    # Keep original image size if available (useful for downstream consumers)
    if original_width and original_height and "image_size" not in internal:
        internal["image_size"] = [original_width, original_height]

    # Persist chosen correction for traceability
    if rotation_correction and rotation_correction != "0":
        internal["rotation_correction"] = rotation_correction

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

    # Informative: count discard markers
    discard_count = 0
    for folder, items in grouped.items():
        for _, ann in items.items():
            if isinstance(ann, dict) and ann.get("discard") is True:
                discard_count += 1
    if discard_count:
        print(f"Marked {discard_count} images as discard")

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

        for image_key, ann in annotations.items():
            if isinstance(ann, dict) and ann.get("discard") is True:
                # Remove the image annotation if it exists
                if image_key in merged[watch_folder]:
                    del merged[watch_folder][image_key]
                continue
            merged[watch_folder][image_key] = ann

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


# --- Discarded image deletion helper ---
def delete_discarded_images(
    new_annotations: Dict[str, Dict[str, Any]],
    images_dir: Path,
) -> None:
    """Delete discarded image files from the local images library.

    We look for discard markers in `new_annotations` (the freshly converted export).
    For each discarded item, we attempt to delete files under:
        images_dir/<watch_folder>/<full_image_name>.*

    Safety:
      - Only deletes within `images_dir`.
      - Skips if `full_image_name` is missing.
    """
    images_dir = images_dir.resolve()
    if not images_dir.exists():
        print(f"Warning: images_dir does not exist, skipping deletes: {images_dir}")
        return

    deleted = 0
    missing = 0

    for watch_folder, items in new_annotations.items():
        for image_key, ann in items.items():
            if not (isinstance(ann, dict) and ann.get("discard") is True):
                continue

            full_image_name = ann.get("full_image_name")
            if not full_image_name:
                print(f"Warning: discard marker missing full_image_name for {watch_folder}/{image_key}; skipping")
                continue

            folder_path = (images_dir / watch_folder).resolve()
            # Safety: ensure folder_path is inside images_dir
            try:
                folder_path.relative_to(images_dir)
            except ValueError:
                print(f"Warning: computed folder outside images_dir, skipping: {folder_path}")
                continue

            candidates = list(folder_path.glob(f"{full_image_name}.*"))
            if not candidates:
                missing += 1
                continue

            for p in candidates:
                try:
                    p.unlink()
                    deleted += 1
                    print(f"Deleted image: {p}")
                except Exception as e:
                    print(f"Warning: failed to delete {p}: {e}")

    if deleted or missing:
        print(f"Discard delete summary: deleted={deleted}, not_found={missing}")


def is_face_or_tiltface(filename: str) -> bool:
    """Check if filename is a face or tiltface view.

    Args:
        filename: Image filename

    Returns:
        True if face or tiltface view based on filename pattern
    """
    # Pattern: BRAND_model_num_viewnum_viewtype_qN.jpg or BRAND_model_num_viewnum_viewtype.jpg
    # We're looking for viewtype = "face" or "tiltface"
    pattern = r'_([a-z]+)(?:_q[123])?\.jpg$'
    match = re.search(pattern, filename.lower())
    if match:
        view_type = match.group(1)
        return view_type in ["face", "tiltface"]
    return False


def remove_discard_markers(
    annotations: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Remove discard markers from annotations.

    When deleting discarded images, we also want to remove the discard markers
    from the final annotation files.

    Args:
        annotations: Dict mapping watch_folder -> {image_key -> annotation}

    Returns:
        Updated annotations dict with discard markers removed
    """
    cleaned = {}
    discard_count = 0

    for watch_folder, watch_annotations in annotations.items():
        cleaned[watch_folder] = {}
        for image_key, ann in watch_annotations.items():
            if isinstance(ann, dict) and ann.get("discard") is True:
                discard_count += 1
                continue
            cleaned[watch_folder][image_key] = ann

    if discard_count:
        print(f"Removed {discard_count} discard markers from annotations")

    return cleaned


def delete_watches_with_few_images(
    annotations: Dict[str, Dict[str, Any]],
    images_dir: Path,
    min_images: int = 2,
) -> Dict[str, Dict[str, Any]]:
    """Delete watch directories with fewer than minimum images.

    After discarding images, some watches may have too few images remaining.
    This function checks both the filesystem AND annotations to find watches to delete.

    Args:
        annotations: Dict mapping watch_folder -> {image_key -> annotation}
        images_dir: Root directory containing watch image folders
        min_images: Minimum number of images required (default: 2)

    Returns:
        Updated annotations dict with deleted watches removed
    """
    images_dir = images_dir.resolve()

    watches_deleted_from_disk = 0
    images_deleted_from_disk = 0
    watches_to_remove = set()

    print(f"\nScanning for watches with < {min_images} face/tiltface images...")

    # Step 1: Check filesystem for watches with < min_images
    if images_dir.exists():
        watch_folders = [d for d in images_dir.iterdir() if d.is_dir()]
        print(f"  Checking {len(watch_folders)} watch directories on disk...")

        for watch_folder in sorted(watch_folders):
            if not watch_folder.is_dir():
                continue

            # Count face/tiltface images only (skip back views)
            face_images = [
                img for img in watch_folder.glob("*.jpg")
                if is_face_or_tiltface(img.name)
            ]

            if len(face_images) < min_images:
                print(f"    Deleting {watch_folder.name} (only {len(face_images)} image(s) on disk)")

                # Count all images for reporting
                all_images = list(watch_folder.glob("*.jpg"))
                total_images_in_dir = len(all_images)

                # Delete the entire directory
                try:
                    shutil.rmtree(watch_folder)
                    watches_deleted_from_disk += 1
                    images_deleted_from_disk += total_images_in_dir
                    watches_to_remove.add(watch_folder.name)
                except Exception as e:
                    print(f"    Failed to delete {watch_folder}: {e}")
    else:
        print(f"  Images directory not found: {images_dir}")

    # Step 2: Check annotations for watches with < min_images (excluding discards)
    print(f"  Checking annotations for watches with < {min_images} annotations...")
    watches_removed_from_annotations = 0

    for watch_folder, watch_annotations in list(annotations.items()):
        # Count non-discarded annotations only
        non_discarded = [
            ann for ann in watch_annotations.values()
            if not (isinstance(ann, dict) and ann.get("discard") is True)
        ]

        if len(non_discarded) < min_images:
            print(f"    Removing {watch_folder} from annotations (only {len(non_discarded)} annotation(s))")
            watches_to_remove.add(watch_folder)
            watches_removed_from_annotations += 1

    # Remove all identified watches from annotations
    updated_annotations = {
        watch_folder: data
        for watch_folder, data in annotations.items()
        if watch_folder not in watches_to_remove
    }

    # Print summary
    total_watches_removed = len(watches_to_remove)
    if total_watches_removed > 0:
        print(f"\nWatch deletion summary:")
        print(f"  Watches deleted from disk: {watches_deleted_from_disk} ({images_deleted_from_disk} total images)")
        print(f"  Watches removed from annotations only: {watches_removed_from_annotations}")
        print(f"  Total watches removed: {total_watches_removed}")
    else:
        print(f"\nNo watches with < {min_images} images found")

    return updated_annotations


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
    parser.add_argument(
        "--delete-discarded-images",
        action="store_true",
        help="If set, delete images marked as discard from the local images library",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=None,
        help="Path to the images library root (default: <repo>/downloaded_images)",
    )

    args = parser.parse_args()

    input_file = args.input
    output_dir = args.output_dir.resolve()

    # Default images library root: watch-image-tagging-tool/downloaded_images
    default_images_dir = Path(__file__).resolve().parents[1] / "downloaded_images"
    images_dir = (args.images_dir or default_images_dir).resolve()

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

    # Optionally delete discarded images from the local images library
    if args.delete_discarded_images:
        delete_discarded_images(new_annotations, images_dir)
        # Remove discard markers from annotations before saving
        annotations = remove_discard_markers(annotations)
        # After deleting discarded images, also delete watches with < 2 images
        annotations = delete_watches_with_few_images(annotations, images_dir, min_images=2)

    # Save
    save_annotations(annotations, output_dir)

    print("Done!")
    return 0


if __name__ == "__main__":
    exit(main())
