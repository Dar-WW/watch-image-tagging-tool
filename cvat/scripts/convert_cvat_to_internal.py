#!/usr/bin/env python3
"""Convert CVAT annotations back to internal JSON format.

This script reads CVAT XML exports and converts them back to our internal
annotation format with normalized coordinates.

Usage:
    python convert_cvat_to_internal.py --input exported.xml --output ./alignment_labels/
    python convert_cvat_to_internal.py --input ./cvat_exports/ --output ./alignment_labels/
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cvat.scripts.config import (
    ALIGNMENT_LABELS_DIR, KEYPOINT_ORDER, LABEL_NAME, QUALITY_REVERSE_MAP
)


def parse_cvat_xml(xml_path: Path) -> Dict:
    """Parse CVAT XML annotation file.
    
    Args:
        xml_path: Path to CVAT XML file
        
    Returns:
        Dictionary of annotations keyed by image name
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    annotations = {}
    
    for image_elem in root.findall(".//image"):
        image_name = image_elem.get("name", "")
        image_width = int(image_elem.get("width", 0))
        image_height = int(image_elem.get("height", 0))
        
        if not image_name or image_width == 0 or image_height == 0:
            continue
        
        # Find skeleton annotations
        for skeleton in image_elem.findall(".//skeleton"):
            label = skeleton.get("label", "")
            
            if label != LABEL_NAME:
                continue
            
            # Extract attributes
            attributes = {}
            for attr in skeleton.findall("attribute"):
                attr_name = attr.get("name")
                attr_value = attr.text
                if attr_name and attr_value:
                    attributes[attr_name] = attr_value
            
            # Extract keypoints
            coords_pixel = {}
            for points_elem in skeleton.findall("points"):
                point_label = points_elem.get("label", "")
                points_str = points_elem.get("points", "")
                
                if point_label and points_str:
                    try:
                        x_str, y_str = points_str.split(",")
                        coords_pixel[point_label] = [float(x_str), float(y_str)]
                    except ValueError:
                        continue
            
            # Store annotation
            annotations[image_name] = {
                "image_size": [image_width, image_height],
                "coords_pixel": coords_pixel,
                "attributes": attributes
            }
    
    return annotations


def extract_image_id(filename: str) -> Optional[str]:
    """Extract image ID from filename (without quality suffix).
    
    Args:
        filename: Image filename (e.g., "PATEK_nab_001_01_face_q3.jpg")
        
    Returns:
        Image ID (e.g., "PATEK_nab_001_01") or None
    """
    # Remove extension
    name = filename.rsplit('.', 1)[0]
    parts = name.split('_')
    
    if len(parts) >= 4:
        # Format: BRAND_collection_NUM_IMGNUM_viewtype_quality
        # Return: BRAND_collection_NUM_IMGNUM
        return '_'.join(parts[:4])
    
    return None


def extract_watch_id(filename: str) -> Optional[str]:
    """Extract watch ID from filename.
    
    Args:
        filename: Image filename (e.g., "PATEK_nab_001_01_face_q3.jpg")
        
    Returns:
        Watch ID (e.g., "PATEK_nab_001") or None
    """
    # Remove extension
    name = filename.rsplit('.', 1)[0]
    parts = name.split('_')
    
    if len(parts) >= 3:
        # Format: BRAND_collection_NUM_...
        return '_'.join(parts[:3])
    
    return None


def normalize_coordinates(coords_pixel: Dict, image_size: Tuple[int, int]) -> Dict:
    """Convert pixel coordinates to normalized [0, 1] range.
    
    Args:
        coords_pixel: Dictionary of pixel coordinates
        image_size: (width, height) in pixels
        
    Returns:
        Dictionary of normalized coordinates
    """
    width, height = image_size
    coords_norm = {}
    
    for key, (x, y) in coords_pixel.items():
        coords_norm[key] = [x / width, y / height]
    
    return coords_norm


def convert_to_internal_format(cvat_annotations: Dict) -> Dict[str, Dict]:
    """Convert CVAT annotations to internal format, grouped by watch.
    
    Args:
        cvat_annotations: Dictionary of CVAT annotations keyed by filename
        
    Returns:
        Dictionary of internal annotations keyed by watch_id,
        with each watch containing annotations keyed by image_id
    """
    watches = {}
    
    for filename, annotation in cvat_annotations.items():
        watch_id = extract_watch_id(filename)
        image_id = extract_image_id(filename)
        
        if not watch_id or not image_id:
            print(f"  Warning: Could not parse filename: {filename}")
            continue
        
        if watch_id not in watches:
            watches[watch_id] = {}
        
        # Convert coordinates
        image_size = tuple(annotation["image_size"])
        coords_pixel = annotation["coords_pixel"]
        coords_norm = normalize_coordinates(coords_pixel, image_size)
        
        # Build internal annotation format
        internal_annotation = {
            "image_size": list(image_size),
            "coords_norm": coords_norm,
            "annotator": "cvat",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "full_image_name": filename.rsplit('.', 1)[0]
        }
        
        # Add quality from attributes if available
        attributes = annotation.get("attributes", {})
        if "quality" in attributes:
            quality_str = attributes["quality"]
            quality_code = QUALITY_REVERSE_MAP.get(quality_str)
            if quality_code:
                internal_annotation["quality"] = quality_code
        
        # Add view_type from attributes if available
        if "view_type" in attributes:
            internal_annotation["view_type"] = attributes["view_type"]
        
        watches[watch_id][image_id] = internal_annotation
    
    return watches


def save_internal_annotations(
    watch_id: str,
    annotations: Dict,
    output_dir: Path,
    merge: bool = True
) -> bool:
    """Save annotations in internal format.
    
    Args:
        watch_id: Watch folder name
        annotations: Dictionary of annotations keyed by image_id
        output_dir: Output directory
        merge: If True, merge with existing annotations
        
    Returns:
        True if successful
    """
    output_path = output_dir / f"{watch_id}.json"
    
    # Load existing annotations if merging
    existing = {}
    if merge and output_path.exists():
        try:
            with open(output_path, 'r') as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    # Merge annotations
    merged = {**existing, **annotations}
    
    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(merged, f, indent=2)
    
    return True


def convert_file(input_path: Path, output_dir: Path, merge: bool = True) -> int:
    """Convert a single CVAT XML file.
    
    Args:
        input_path: Path to CVAT XML file
        output_dir: Output directory for internal JSON files
        merge: If True, merge with existing annotations
        
    Returns:
        Number of annotations converted
    """
    print(f"Converting {input_path.name}...")
    
    # Parse CVAT XML
    cvat_annotations = parse_cvat_xml(input_path)
    
    if not cvat_annotations:
        print(f"  No annotations found")
        return 0
    
    print(f"  Found {len(cvat_annotations)} image annotations")
    
    # Convert to internal format
    watches = convert_to_internal_format(cvat_annotations)
    
    # Save each watch
    total_saved = 0
    for watch_id, annotations in watches.items():
        if save_internal_annotations(watch_id, annotations, output_dir, merge):
            print(f"  Saved {len(annotations)} annotations for {watch_id}")
            total_saved += len(annotations)
    
    return total_saved


def main():
    parser = argparse.ArgumentParser(
        description="Convert CVAT annotations to internal format"
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input CVAT XML file or directory"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ALIGNMENT_LABELS_DIR),
        help="Output directory for internal JSON files"
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Don't merge with existing annotations (overwrite)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate converted annotations"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_dir = Path(args.output)
    merge = not args.no_merge
    
    # Process input
    if input_path.is_file():
        count = convert_file(input_path, output_dir, merge)
        print(f"\nConverted {count} annotations")
    elif input_path.is_dir():
        total_count = 0
        xml_files = list(input_path.glob("*.xml"))
        
        if not xml_files:
            print(f"No XML files found in {input_path}")
            sys.exit(1)
        
        print(f"Found {len(xml_files)} XML files")
        
        for xml_file in xml_files:
            count = convert_file(xml_file, output_dir, merge)
            total_count += count
        
        print(f"\nTotal: Converted {total_count} annotations")
    else:
        print(f"Input not found: {input_path}")
        sys.exit(1)
    
    # Optionally validate
    if args.validate:
        print("\nRunning validation...")
        from validate_annotations import validate_all
        validate_all(output_dir)


if __name__ == "__main__":
    main()
