#!/usr/bin/env python3
"""Convert internal JSON annotations to CVAT format.

This script reads our internal annotation format and converts it to
CVAT-compatible XML (CVAT for images 1.1 format) for import.

Usage:
    python convert_internal_to_cvat.py [--watch WATCH_ID] [--output OUTPUT_DIR]
    python convert_internal_to_cvat.py --all --output ./cvat_exports
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from PIL import Image

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cvat.scripts.config import (
    IMAGES_DIR, ALIGNMENT_LABELS_DIR, KEYPOINT_ORDER, 
    LABEL_NAME, QUALITY_MAP
)


def load_internal_annotations(watch_id: str) -> Dict:
    """Load internal annotations for a watch.
    
    Args:
        watch_id: Watch folder name (e.g., "PATEK_nab_001")
        
    Returns:
        Dictionary of annotations keyed by image ID
    """
    json_path = ALIGNMENT_LABELS_DIR / f"{watch_id}.json"
    
    if not json_path.exists():
        return {}
    
    with open(json_path, 'r') as f:
        return json.load(f)


def get_image_info(watch_id: str, image_id: str) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """Get image filename and dimensions.
    
    Args:
        watch_id: Watch folder name
        image_id: Image ID (e.g., "PATEK_nab_001_01")
        
    Returns:
        Tuple of (filename, (width, height)) or (None, None) if not found
    """
    watch_dir = IMAGES_DIR / watch_id
    
    if not watch_dir.exists():
        return None, None
    
    # Find image file matching the ID (could have different quality suffix)
    for img_file in watch_dir.glob(f"{image_id}_*.jpg"):
        try:
            with Image.open(img_file) as img:
                return img_file.name, img.size
        except Exception:
            continue
    
    return None, None


def parse_filename(filename: str) -> Dict:
    """Parse watch image filename to extract metadata.
    
    Args:
        filename: Image filename (e.g., "PATEK_nab_001_01_face_q3.jpg")
        
    Returns:
        Dictionary with parsed metadata
    """
    # Remove extension
    name = filename.rsplit('.', 1)[0]
    parts = name.split('_')
    
    result = {
        'watch_id': None,
        'image_num': None,
        'view_type': None,
        'quality': None
    }
    
    if len(parts) >= 4:
        # Format: BRAND_collection_NUM_IMGNUM_viewtype_quality
        # e.g., PATEK_nab_001_01_face_q3
        result['watch_id'] = '_'.join(parts[:3])  # PATEK_nab_001
        result['image_num'] = parts[3]  # 01
        
        if len(parts) >= 5:
            result['view_type'] = parts[4]  # face or tiltface
            
        if len(parts) >= 6 and parts[5].startswith('q'):
            result['quality'] = int(parts[5][1])  # 1, 2, or 3
    
    return result


def normalize_to_absolute(coords_norm: Dict, image_size: Tuple[int, int]) -> Dict:
    """Convert normalized coordinates to absolute pixel coordinates.
    
    Args:
        coords_norm: Dictionary of normalized coordinates
        image_size: (width, height) in pixels
        
    Returns:
        Dictionary of absolute pixel coordinates
    """
    width, height = image_size
    coords_abs = {}
    
    for key, (x_norm, y_norm) in coords_norm.items():
        coords_abs[key] = (
            x_norm * width,
            y_norm * height
        )
    
    return coords_abs


def create_cvat_xml(watch_id: str, annotations: Dict, output_path: Path) -> bool:
    """Create CVAT XML annotation file.
    
    Args:
        watch_id: Watch folder name
        annotations: Internal annotations dictionary
        output_path: Path to write XML file
        
    Returns:
        True if successful, False otherwise
    """
    # Create root element
    root = ET.Element("annotations")
    
    # Add version info
    version = ET.SubElement(root, "version")
    version.text = "1.1"
    
    # Add meta information
    meta = ET.SubElement(root, "meta")
    task = ET.SubElement(meta, "task")
    
    # Task metadata
    task_name = ET.SubElement(task, "name")
    task_name.text = watch_id
    
    created = ET.SubElement(task, "created")
    created.text = datetime.now().isoformat()
    
    source = ET.SubElement(task, "source")
    source.text = "internal_migration"
    
    # Add labels definition
    labels_elem = ET.SubElement(task, "labels")
    label = ET.SubElement(labels_elem, "label")
    label_name = ET.SubElement(label, "name")
    label_name.text = LABEL_NAME
    label_type = ET.SubElement(label, "type")
    label_type.text = "skeleton"
    
    # Add sublabels (keypoints)
    for keypoint in KEYPOINT_ORDER:
        sublabel = ET.SubElement(label, "sublabel")
        sublabel_name = ET.SubElement(sublabel, "name")
        sublabel_name.text = keypoint
    
    # Process each image annotation
    image_id_counter = 0
    
    for image_id, annotation in annotations.items():
        # Get actual image file and dimensions
        filename, actual_size = get_image_info(watch_id, image_id)
        
        if filename is None:
            print(f"  Warning: Image not found for {image_id}, skipping")
            continue
        
        # Get stored image size (what was annotated against)
        stored_size = tuple(annotation.get("image_size", [0, 0]))
        
        # Use actual image size for CVAT (they should match, but be safe)
        if actual_size and stored_size:
            width, height = actual_size
        else:
            width, height = stored_size or (0, 0)
        
        if width == 0 or height == 0:
            print(f"  Warning: Invalid image size for {image_id}, skipping")
            continue
        
        # Create image element
        image_elem = ET.SubElement(root, "image")
        image_elem.set("id", str(image_id_counter))
        image_elem.set("name", filename)
        image_elem.set("width", str(width))
        image_elem.set("height", str(height))
        
        # Parse filename for attributes
        file_meta = parse_filename(filename)
        
        # Convert normalized coords to absolute
        coords_norm = annotation.get("coords_norm", {})
        coords_abs = normalize_to_absolute(coords_norm, (width, height))
        
        # Create skeleton element
        skeleton = ET.SubElement(image_elem, "skeleton")
        skeleton.set("label", LABEL_NAME)
        skeleton.set("source", "manual")
        skeleton.set("occluded", "0")
        skeleton.set("z_order", "0")
        
        # Add attributes
        if file_meta['quality']:
            quality_attr = ET.SubElement(skeleton, "attribute")
            quality_attr.set("name", "quality")
            quality_attr.text = QUALITY_MAP.get(file_meta['quality'], "full")
        
        if file_meta['view_type']:
            view_attr = ET.SubElement(skeleton, "attribute")
            view_attr.set("name", "view_type")
            view_attr.text = file_meta['view_type']
        
        # Add points (keypoints)
        for keypoint in KEYPOINT_ORDER:
            if keypoint in coords_abs:
                x, y = coords_abs[keypoint]
                
                point = ET.SubElement(skeleton, "points")
                point.set("label", keypoint)
                point.set("source", "manual")
                point.set("occluded", "0")
                point.set("outside", "0")
                point.set("points", f"{x:.2f},{y:.2f}")
        
        image_id_counter += 1
    
    if image_id_counter == 0:
        print(f"  Warning: No valid annotations found for {watch_id}")
        return False
    
    # Write XML file
    xml_str = ET.tostring(root, encoding='unicode')
    pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="  ")
    
    # Remove extra blank lines
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    pretty_xml = '\n'.join(lines)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)
    
    print(f"  Exported {image_id_counter} annotations to {output_path}")
    return True


def convert_watch(watch_id: str, output_dir: Path) -> bool:
    """Convert annotations for a single watch.
    
    Args:
        watch_id: Watch folder name
        output_dir: Directory to write output files
        
    Returns:
        True if successful, False otherwise
    """
    print(f"Converting {watch_id}...")
    
    # Load internal annotations
    annotations = load_internal_annotations(watch_id)
    
    if not annotations:
        print(f"  No annotations found for {watch_id}")
        return False
    
    print(f"  Found {len(annotations)} annotations")
    
    # Create CVAT XML
    output_path = output_dir / f"{watch_id}_annotations.xml"
    return create_cvat_xml(watch_id, annotations, output_path)


def get_all_watch_ids() -> List[str]:
    """Get list of all watch IDs with annotations."""
    watch_ids = []
    
    if ALIGNMENT_LABELS_DIR.exists():
        for json_file in ALIGNMENT_LABELS_DIR.glob("*.json"):
            if json_file.name != ".gitkeep":
                watch_ids.append(json_file.stem)
    
    return sorted(watch_ids)


def main():
    parser = argparse.ArgumentParser(
        description="Convert internal annotations to CVAT format"
    )
    parser.add_argument(
        "--watch",
        type=str,
        help="Watch ID to convert (e.g., PATEK_nab_001)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Convert all watches with annotations"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./cvat_exports",
        help="Output directory for CVAT XML files"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all watches with annotations"
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    
    # List watches
    if args.list:
        watch_ids = get_all_watch_ids()
        print(f"Found {len(watch_ids)} watches with annotations:")
        for watch_id in watch_ids:
            print(f"  - {watch_id}")
        return
    
    # Convert specific watch
    if args.watch:
        success = convert_watch(args.watch, output_dir)
        sys.exit(0 if success else 1)
    
    # Convert all watches
    if args.all:
        watch_ids = get_all_watch_ids()
        
        if not watch_ids:
            print("No watches with annotations found")
            sys.exit(1)
        
        print(f"Converting {len(watch_ids)} watches...")
        
        success_count = 0
        for watch_id in watch_ids:
            if convert_watch(watch_id, output_dir):
                success_count += 1
        
        print(f"\nConverted {success_count}/{len(watch_ids)} watches")
        sys.exit(0 if success_count > 0 else 1)
    
    # No action specified
    parser.print_help()


if __name__ == "__main__":
    main()
