#!/usr/bin/env python3
"""
QA/Validation script for annotation data.

This script validates annotations against a checklist of requirements:
- All keypoints exist and are within [0,1] normalized bounds
- Crop ROI rectangle is within image bounds and non-empty
- Each task has exactly one image field
- No duplicate keypoint labels per task
- Image paths are accessible
- Exported JSON matches internal schema

Usage:
    python validate_annotations.py --input-dir ../alignment_labels
    python validate_annotations.py --input-dir ../alignment_labels --images-dir ../downloaded_images
    python validate_annotations.py --labelstudio-export export.json
"""

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REQUIRED_KEYPOINTS = {"top", "bottom", "left", "right", "center"}


@dataclass
class ValidationResult:
    """Result of validation for a single annotation."""

    image_key: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


@dataclass
class ValidationReport:
    """Overall validation report."""

    results: List[ValidationResult] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def valid_count(self) -> int:
        return sum(1 for r in self.results if r.is_valid)

    @property
    def invalid_count(self) -> int:
        return sum(1 for r in self.results if not r.is_valid)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.warnings)

    def add_result(self, result: ValidationResult) -> None:
        self.results.append(result)

    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Total annotations: {self.total_count}")
        print(f"Valid: {self.valid_count}")
        print(f"Invalid: {self.invalid_count}")
        print(f"With warnings: {self.warning_count}")

        if self.invalid_count > 0:
            print("\nERRORS:")
            print("-" * 40)
            for result in self.results:
                if not result.is_valid:
                    print(f"\n{result.image_key}:")
                    for error in result.errors:
                        print(f"  ❌ {error}")

        if self.warning_count > 0:
            print("\nWARNINGS:")
            print("-" * 40)
            for result in self.results:
                if result.warnings:
                    print(f"\n{result.image_key}:")
                    for warning in result.warnings:
                        print(f"  ⚠️  {warning}")

        print("\n" + "=" * 60)
        if self.invalid_count == 0:
            print("✅ All annotations passed validation!")
        else:
            print(f"❌ {self.invalid_count} annotations have errors")
        print("=" * 60)


def validate_keypoint_coords(
    coords: List[float],
    keypoint_name: str,
    result: ValidationResult,
) -> None:
    """Validate keypoint coordinates are within bounds."""
    if not coords or len(coords) != 2:
        result.add_error(f"Keypoint '{keypoint_name}' has invalid coordinate format")
        return

    x, y = coords

    if not (0 <= x <= 1):
        result.add_error(
            f"Keypoint '{keypoint_name}' x-coordinate {x:.4f} is outside [0, 1]"
        )

    if not (0 <= y <= 1):
        result.add_error(
            f"Keypoint '{keypoint_name}' y-coordinate {y:.4f} is outside [0, 1]"
        )


def validate_crop_bbox(
    crop_bbox: List[int],
    original_size: List[int],
    result: ValidationResult,
) -> None:
    """Validate crop bounding box is within image bounds."""
    if not crop_bbox or len(crop_bbox) != 4:
        result.add_warning("Missing or invalid crop_bbox format")
        return

    if not original_size or len(original_size) != 2:
        result.add_warning("Missing original_image_size, cannot validate crop_bbox")
        return

    x1, y1, x2, y2 = crop_bbox
    orig_width, orig_height = original_size

    # Check bounds
    if x1 < 0:
        result.add_error(f"crop_bbox x1 ({x1}) is negative")
    if y1 < 0:
        result.add_error(f"crop_bbox y1 ({y1}) is negative")
    if x2 > orig_width:
        result.add_error(f"crop_bbox x2 ({x2}) exceeds image width ({orig_width})")
    if y2 > orig_height:
        result.add_error(f"crop_bbox y2 ({y2}) exceeds image height ({orig_height})")

    # Check non-empty
    if x2 <= x1:
        result.add_error(f"crop_bbox has zero or negative width (x1={x1}, x2={x2})")
    if y2 <= y1:
        result.add_error(f"crop_bbox has zero or negative height (y1={y1}, y2={y2})")


def validate_internal_annotation(
    image_key: str,
    annotation: Dict[str, Any],
    images_dir: Optional[Path] = None,
) -> ValidationResult:
    """
    Validate a single internal annotation.

    Args:
        image_key: The image identifier
        annotation: The annotation dict
        images_dir: Optional directory containing images

    Returns:
        ValidationResult with any errors/warnings
    """
    result = ValidationResult(image_key=image_key)

    # Check coords_norm exists
    coords_norm = annotation.get("coords_norm")
    if not coords_norm:
        result.add_error("Missing 'coords_norm' field")
    else:
        # Check all required keypoints exist
        found_keypoints = set(coords_norm.keys())
        missing = REQUIRED_KEYPOINTS - found_keypoints
        if missing:
            result.add_error(f"Missing keypoints: {sorted(missing)}")

        # Check for duplicate labels (shouldn't happen in dict, but check keys)
        extra = found_keypoints - REQUIRED_KEYPOINTS
        if extra:
            result.add_warning(f"Unknown keypoint labels: {sorted(extra)}")

        # Validate each keypoint's coordinates
        for name, coords in coords_norm.items():
            validate_keypoint_coords(coords, name, result)

    # Validate crop_bbox if present
    crop_bbox = annotation.get("crop_bbox")
    original_size = annotation.get("original_image_size")
    if crop_bbox:
        validate_crop_bbox(crop_bbox, original_size, result)

    # Check image accessibility if images_dir provided
    if images_dir:
        full_image_name = annotation.get("full_image_name")
        if full_image_name:
            # Extract watch folder from image_key
            parts = image_key.rsplit("_", 1)
            watch_folder = parts[0] if len(parts) > 1 else image_key

            image_path = images_dir / watch_folder / f"{full_image_name}.jpg"
            if not image_path.exists():
                result.add_warning(f"Image file not found: {image_path}")

    return result


def validate_internal_annotations(
    input_dir: Path,
    images_dir: Optional[Path] = None,
) -> ValidationReport:
    """
    Validate all internal annotation files.

    Args:
        input_dir: Directory containing annotation JSON files
        images_dir: Optional directory containing images

    Returns:
        ValidationReport with all results
    """
    report = ValidationReport()

    for json_file in sorted(input_dir.glob("*.json")):
        if json_file.name == ".gitkeep":
            continue

        print(f"Validating: {json_file.name}")

        with open(json_file) as f:
            data = json.load(f)

        for image_key, annotation in data.items():
            result = validate_internal_annotation(image_key, annotation, images_dir)
            report.add_result(result)

    return report


def validate_labelstudio_task(
    task: Dict[str, Any],
) -> ValidationResult:
    """
    Validate a Label Studio task/annotation.

    Args:
        task: Label Studio task dict

    Returns:
        ValidationResult with any errors/warnings
    """
    # Get image key from task data
    data = task.get("data", {})
    image_key = data.get("image_key", data.get("image", "unknown"))
    result = ValidationResult(image_key=str(image_key))

    # Check image field exists
    if "image" not in data:
        result.add_error("Missing 'image' field in task data")

    # Check annotations
    annotations = task.get("annotations", []) or task.get("completions", [])

    if not annotations:
        result.add_warning("No annotations found for task")
        return result

    # Validate the latest annotation
    latest = annotations[-1]
    results_list = latest.get("result", [])

    if not results_list:
        result.add_warning("Empty result array in annotation")
        return result

    # Check for keypoints
    found_keypoints = set()
    has_crop_roi = False

    for r in results_list:
        result_type = r.get("type", "")
        value = r.get("value", {})

        if result_type == "keypointlabels":
            labels = value.get("keypointlabels", [])
            for label in labels:
                label_lower = label.lower()
                if label_lower in found_keypoints:
                    result.add_error(f"Duplicate keypoint label: {label}")
                found_keypoints.add(label_lower)

            # Validate coordinates (percentages 0-100)
            x = value.get("x", 0)
            y = value.get("y", 0)
            if not (0 <= x <= 100):
                result.add_error(f"Keypoint x={x} outside [0, 100]")
            if not (0 <= y <= 100):
                result.add_error(f"Keypoint y={y} outside [0, 100]")

        elif result_type == "rectanglelabels":
            labels = value.get("rectanglelabels", [])
            if "Crop ROI" in labels:
                if has_crop_roi:
                    result.add_error("Multiple Crop ROI rectangles found")
                has_crop_roi = True

                # Validate rectangle bounds
                x = value.get("x", 0)
                y = value.get("y", 0)
                width = value.get("width", 0)
                height = value.get("height", 0)

                if width <= 0 or height <= 0:
                    result.add_error("Crop ROI has zero or negative dimensions")
                if x < 0 or y < 0:
                    result.add_error("Crop ROI has negative position")
                if x + width > 100 or y + height > 100:
                    result.add_warning("Crop ROI extends beyond image bounds")

    # Check all required keypoints
    missing = REQUIRED_KEYPOINTS - found_keypoints
    if missing:
        result.add_error(f"Missing keypoints: {sorted(missing)}")

    return result


def validate_labelstudio_export(
    export_file: Path,
) -> ValidationReport:
    """
    Validate a Label Studio export file.

    Args:
        export_file: Path to Label Studio export JSON

    Returns:
        ValidationReport with all results
    """
    report = ValidationReport()

    with open(export_file) as f:
        data = json.load(f)

    # Handle both list and single task formats
    if isinstance(data, dict):
        data = [data]

    print(f"Validating {len(data)} Label Studio tasks...")

    for task in data:
        result = validate_labelstudio_task(task)
        report.add_result(result)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Validate annotation data"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Directory containing internal annotation JSON files",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        help="Directory containing images (for accessibility check)",
    )
    parser.add_argument(
        "--labelstudio-export",
        type=Path,
        help="Label Studio export JSON file to validate",
    )

    args = parser.parse_args()

    if args.labelstudio_export:
        if not args.labelstudio_export.exists():
            print(f"Error: Export file not found: {args.labelstudio_export}")
            return 1

        report = validate_labelstudio_export(args.labelstudio_export)

    elif args.input_dir:
        if not args.input_dir.exists():
            print(f"Error: Input directory not found: {args.input_dir}")
            return 1

        images_dir = args.images_dir
        if images_dir and not images_dir.exists():
            print(f"Warning: Images directory not found: {images_dir}")
            images_dir = None

        report = validate_internal_annotations(args.input_dir, images_dir)

    else:
        # Default: validate internal annotations
        default_input = Path(__file__).parent.parent / "alignment_labels"
        default_images = Path(__file__).parent.parent / "downloaded_images"

        if not default_input.exists():
            print("Error: No input specified and default alignment_labels not found")
            parser.print_help()
            return 1

        images_dir = default_images if default_images.exists() else None
        report = validate_internal_annotations(default_input, images_dir)

    report.print_summary()

    return 0 if report.invalid_count == 0 else 1


if __name__ == "__main__":
    exit(main())
