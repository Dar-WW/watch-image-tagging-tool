#!/usr/bin/env python3
"""Validate annotation quality and consistency.

This script checks annotations for:
- Missing keypoints
- Out-of-bounds coordinates
- Suspicious placements (e.g., all points in same location)
- Consistency between image files and annotations

Usage:
    python validate_annotations.py [--watch WATCH_ID]
    python validate_annotations.py --all
    python validate_annotations.py --summary
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image
from dataclasses import dataclass
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cvat.scripts.config import (
    IMAGES_DIR, ALIGNMENT_LABELS_DIR, KEYPOINT_ORDER, LABEL_NAME
)


class IssueType(Enum):
    MISSING_KEYPOINTS = "missing_keypoints"
    OUT_OF_BOUNDS = "out_of_bounds"
    SUSPICIOUS_PLACEMENT = "suspicious_placement"
    DUPLICATE_POINTS = "duplicate_points"
    IMAGE_NOT_FOUND = "image_not_found"
    SIZE_MISMATCH = "size_mismatch"
    INCOMPLETE_ANNOTATION = "incomplete_annotation"


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    issue_type: IssueType
    image_id: str
    watch_id: str
    message: str
    severity: str  # "error", "warning", "info"
    
    def __str__(self):
        return f"[{self.severity.upper()}] {self.watch_id}/{self.image_id}: {self.message}"


def load_annotations(watch_id: str, labels_dir: Path = None) -> Dict:
    """Load annotations for a watch."""
    if labels_dir is None:
        labels_dir = ALIGNMENT_LABELS_DIR
    
    json_path = labels_dir / f"{watch_id}.json"
    
    if not json_path.exists():
        return {}
    
    with open(json_path, 'r') as f:
        return json.load(f)


def get_image_files(watch_id: str) -> Dict[str, Path]:
    """Get mapping of image IDs to file paths."""
    watch_dir = IMAGES_DIR / watch_id
    
    if not watch_dir.exists():
        return {}
    
    images = {}
    for img_file in watch_dir.glob("*.jpg"):
        # Extract image ID from filename
        name = img_file.stem
        parts = name.split('_')
        if len(parts) >= 4:
            image_id = '_'.join(parts[:4])
            images[image_id] = img_file
    
    return images


def validate_keypoints(
    coords_norm: Dict,
    image_id: str,
    watch_id: str
) -> List[ValidationIssue]:
    """Validate keypoint annotations."""
    issues = []
    
    # Check for missing keypoints
    missing = []
    for keypoint in KEYPOINT_ORDER:
        if keypoint not in coords_norm:
            missing.append(keypoint)
    
    if missing:
        issues.append(ValidationIssue(
            issue_type=IssueType.MISSING_KEYPOINTS,
            image_id=image_id,
            watch_id=watch_id,
            message=f"Missing keypoints: {', '.join(missing)}",
            severity="error"
        ))
    
    # Check for out-of-bounds coordinates
    for keypoint, (x, y) in coords_norm.items():
        if not (0 <= x <= 1 and 0 <= y <= 1):
            issues.append(ValidationIssue(
                issue_type=IssueType.OUT_OF_BOUNDS,
                image_id=image_id,
                watch_id=watch_id,
                message=f"Keypoint '{keypoint}' out of bounds: ({x:.4f}, {y:.4f})",
                severity="error"
            ))
    
    # Check for duplicate/overlapping points
    points = list(coords_norm.values())
    for i, (p1_name, p1) in enumerate(coords_norm.items()):
        for p2_name, p2 in list(coords_norm.items())[i+1:]:
            dist = ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
            if dist < 0.01:  # Very close points (within 1% of image)
                issues.append(ValidationIssue(
                    issue_type=IssueType.DUPLICATE_POINTS,
                    image_id=image_id,
                    watch_id=watch_id,
                    message=f"Points '{p1_name}' and '{p2_name}' are very close (dist={dist:.4f})",
                    severity="warning"
                ))
    
    # Check for suspicious placements
    if len(coords_norm) >= 5:
        # Check if center is reasonably between edges
        if all(k in coords_norm for k in ['top', 'bottom', 'left', 'right', 'center']):
            center = coords_norm['center']
            top = coords_norm['top']
            bottom = coords_norm['bottom']
            left = coords_norm['left']
            right = coords_norm['right']
            
            # Center should be roughly between top/bottom and left/right
            mid_y = (top[1] + bottom[1]) / 2
            mid_x = (left[0] + right[0]) / 2
            
            if abs(center[1] - mid_y) > 0.2:  # More than 20% off from vertical center
                issues.append(ValidationIssue(
                    issue_type=IssueType.SUSPICIOUS_PLACEMENT,
                    image_id=image_id,
                    watch_id=watch_id,
                    message=f"Center y-coordinate {center[1]:.2f} seems off from top/bottom midpoint {mid_y:.2f}",
                    severity="warning"
                ))
            
            if abs(center[0] - mid_x) > 0.2:  # More than 20% off from horizontal center
                issues.append(ValidationIssue(
                    issue_type=IssueType.SUSPICIOUS_PLACEMENT,
                    image_id=image_id,
                    watch_id=watch_id,
                    message=f"Center x-coordinate {center[0]:.2f} seems off from left/right midpoint {mid_x:.2f}",
                    severity="warning"
                ))
    
    return issues


def validate_image_consistency(
    annotation: Dict,
    image_path: Path,
    image_id: str,
    watch_id: str
) -> List[ValidationIssue]:
    """Check consistency between annotation and image file."""
    issues = []
    
    if not image_path.exists():
        issues.append(ValidationIssue(
            issue_type=IssueType.IMAGE_NOT_FOUND,
            image_id=image_id,
            watch_id=watch_id,
            message=f"Image file not found: {image_path.name}",
            severity="error"
        ))
        return issues
    
    # Check image size
    try:
        with Image.open(image_path) as img:
            actual_size = img.size
    except Exception as e:
        issues.append(ValidationIssue(
            issue_type=IssueType.IMAGE_NOT_FOUND,
            image_id=image_id,
            watch_id=watch_id,
            message=f"Could not read image: {e}",
            severity="error"
        ))
        return issues
    
    stored_size = tuple(annotation.get("image_size", [0, 0]))
    
    if stored_size and actual_size != stored_size:
        issues.append(ValidationIssue(
            issue_type=IssueType.SIZE_MISMATCH,
            image_id=image_id,
            watch_id=watch_id,
            message=f"Size mismatch: annotation says {stored_size}, image is {actual_size}",
            severity="warning"
        ))
    
    return issues


def validate_watch(watch_id: str, labels_dir: Path = None) -> Tuple[List[ValidationIssue], Dict]:
    """Validate all annotations for a watch.
    
    Returns:
        Tuple of (issues list, summary dict)
    """
    if labels_dir is None:
        labels_dir = ALIGNMENT_LABELS_DIR
    
    issues = []
    summary = {
        "total_images": 0,
        "annotated_images": 0,
        "complete_annotations": 0,
        "issues_by_type": {}
    }
    
    # Load annotations
    annotations = load_annotations(watch_id, labels_dir)
    
    # Get image files
    image_files = get_image_files(watch_id)
    
    summary["total_images"] = len(image_files)
    summary["annotated_images"] = len(annotations)
    
    # Check each annotation
    for image_id, annotation in annotations.items():
        coords_norm = annotation.get("coords_norm", {})
        
        # Check keypoints
        keypoint_issues = validate_keypoints(coords_norm, image_id, watch_id)
        issues.extend(keypoint_issues)
        
        # Check completeness
        if len(coords_norm) >= 5:
            summary["complete_annotations"] += 1
        else:
            issues.append(ValidationIssue(
                issue_type=IssueType.INCOMPLETE_ANNOTATION,
                image_id=image_id,
                watch_id=watch_id,
                message=f"Only {len(coords_norm)}/5 keypoints annotated",
                severity="warning"
            ))
        
        # Check image consistency
        if image_id in image_files:
            consistency_issues = validate_image_consistency(
                annotation, image_files[image_id], image_id, watch_id
            )
            issues.extend(consistency_issues)
    
    # Check for images without annotations
    for image_id in image_files:
        if image_id not in annotations:
            issues.append(ValidationIssue(
                issue_type=IssueType.INCOMPLETE_ANNOTATION,
                image_id=image_id,
                watch_id=watch_id,
                message="No annotation found for this image",
                severity="info"
            ))
    
    # Count issues by type
    for issue in issues:
        issue_type = issue.issue_type.value
        if issue_type not in summary["issues_by_type"]:
            summary["issues_by_type"][issue_type] = 0
        summary["issues_by_type"][issue_type] += 1
    
    return issues, summary


def get_all_watch_ids(labels_dir: Path = None) -> List[str]:
    """Get list of all watch IDs with annotations."""
    if labels_dir is None:
        labels_dir = ALIGNMENT_LABELS_DIR
    
    if not labels_dir.exists():
        return []
    
    watch_ids = []
    for json_file in labels_dir.glob("*.json"):
        if json_file.name != ".gitkeep":
            watch_ids.append(json_file.stem)
    
    return sorted(watch_ids)


def validate_all(labels_dir: Optional[Path] = None) -> Tuple[List[ValidationIssue], Dict]:
    """Validate all watches."""
    if labels_dir is None:
        labels_dir = ALIGNMENT_LABELS_DIR
    
    all_issues = []
    all_summary = {
        "total_watches": 0,
        "total_images": 0,
        "total_annotated": 0,
        "total_complete": 0,
        "issues_by_severity": {"error": 0, "warning": 0, "info": 0},
        "issues_by_type": {}
    }
    
    watch_ids = get_all_watch_ids(labels_dir)
    all_summary["total_watches"] = len(watch_ids)
    
    for watch_id in watch_ids:
        issues, summary = validate_watch(watch_id, labels_dir)
        all_issues.extend(issues)
        
        all_summary["total_images"] += summary["total_images"]
        all_summary["total_annotated"] += summary["annotated_images"]
        all_summary["total_complete"] += summary["complete_annotations"]
        
        for issue_type, count in summary["issues_by_type"].items():
            if issue_type not in all_summary["issues_by_type"]:
                all_summary["issues_by_type"][issue_type] = 0
            all_summary["issues_by_type"][issue_type] += count
    
    # Count by severity
    for issue in all_issues:
        all_summary["issues_by_severity"][issue.severity] += 1
    
    return all_issues, all_summary


def print_issues(issues: List[ValidationIssue], verbose: bool = False):
    """Print validation issues."""
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    info = [i for i in issues if i.severity == "info"]
    
    if errors:
        print(f"\n🔴 ERRORS ({len(errors)}):")
        for issue in errors[:20]:  # Limit output
            print(f"  {issue}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors")
    
    if warnings and verbose:
        print(f"\n🟡 WARNINGS ({len(warnings)}):")
        for issue in warnings[:20]:
            print(f"  {issue}")
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more warnings")
    
    if info and verbose:
        print(f"\n🔵 INFO ({len(info)}):")
        for issue in info[:10]:
            print(f"  {issue}")
        if len(info) > 10:
            print(f"  ... and {len(info) - 10} more info messages")


def print_summary(summary: Dict, is_single_watch: bool = False):
    """Print validation summary."""
    print("\n" + "="*50)
    print("VALIDATION SUMMARY")
    print("="*50)
    
    print(f"\n📊 Coverage:")
    
    if is_single_watch:
        # Single watch summary
        print(f"  Total images: {summary.get('total_images', 0)}")
        print(f"  Annotated images: {summary.get('annotated_images', 0)}")
        print(f"  Complete annotations (5/5 points): {summary.get('complete_annotations', 0)}")
        
        if summary.get('total_images', 0) > 0:
            coverage = summary.get('annotated_images', 0) / summary['total_images'] * 100
            completeness = summary.get('complete_annotations', 0) / summary['total_images'] * 100
            print(f"\n  Coverage rate: {coverage:.1f}%")
            print(f"  Completeness rate: {completeness:.1f}%")
    else:
        # Aggregate summary (all watches)
        print(f"  Watches with annotations: {summary.get('total_watches', 0)}")
        print(f"  Total images: {summary.get('total_images', 0)}")
        print(f"  Annotated images: {summary.get('total_annotated', 0)}")
        print(f"  Complete annotations (5/5 points): {summary.get('total_complete', 0)}")
        
        if summary.get('total_images', 0) > 0:
            coverage = summary.get('total_annotated', 0) / summary['total_images'] * 100
            completeness = summary.get('total_complete', 0) / summary['total_images'] * 100
            print(f"\n  Coverage rate: {coverage:.1f}%")
            print(f"  Completeness rate: {completeness:.1f}%")
    
    # Count by severity - only available in aggregate summary
    if summary.get('issues_by_severity'):
        print(f"\n⚠️ Issues by severity:")
        for severity, count in summary.get('issues_by_severity', {}).items():
            emoji = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")
            print(f"  {emoji} {severity.capitalize()}: {count}")
    
    if summary.get('issues_by_type'):
        print(f"\n📋 Issues by type:")
        for issue_type, count in summary['issues_by_type'].items():
            print(f"  {issue_type}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate annotation quality"
    )
    parser.add_argument(
        "--watch",
        type=str,
        help="Watch ID to validate"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate all watches"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary only"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show all issues including warnings and info"
    )
    parser.add_argument(
        "--labels-dir",
        type=str,
        help="Custom labels directory"
    )
    
    args = parser.parse_args()
    
    labels_dir = Path(args.labels_dir) if args.labels_dir else ALIGNMENT_LABELS_DIR
    
    # Validate specific watch
    if args.watch:
        print(f"Validating {args.watch}...")
        issues, summary = validate_watch(args.watch, labels_dir)
        
        if not args.summary:
            print_issues(issues, args.verbose)
        
        print_summary(summary, is_single_watch=True)
        
        # Exit with error if there are errors
        error_count = summary.get('issues_by_type', {}).get('error', 0)
        sys.exit(1 if error_count > 0 else 0)
    
    # Validate all watches
    if args.all or args.summary:
        print("Validating all watches...")
        issues, summary = validate_all(labels_dir)
        
        if not args.summary:
            print_issues(issues, args.verbose)
        
        print_summary(summary)
        
        # Exit with error if there are errors
        error_count = summary.get('issues_by_severity', {}).get('error', 0)
        sys.exit(1 if error_count > 0 else 0)
    
    parser.print_help()


if __name__ == "__main__":
    main()
