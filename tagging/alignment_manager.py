"""Alignment annotation manager for watch images.

Handles loading, saving, and managing alignment keypoint annotations.
Annotations are stored in JSON files per watch with normalized coordinates.
"""

import os
import json
from typing import List, Optional, Tuple, Dict
from pathlib import Path
from datetime import datetime, timezone

try:
    from .filename_parser import ImageMetadata
except ImportError:
    from filename_parser import ImageMetadata


class AlignmentManager:
    """Manages alignment annotations for watch images."""

    def __init__(self, labels_dir: str = None):
        """Initialize AlignmentManager.

        Args:
            labels_dir: Path to alignment_labels directory.
                       If None, uses ../alignment_labels relative to this file.
        """
        if labels_dir is None:
            # Default to alignment_labels in parent directory of this repo
            current_dir = Path(__file__).parent.parent
            labels_dir = os.path.join(current_dir, "alignment_labels")

        self.labels_dir = labels_dir

        # Create directory if it doesn't exist
        os.makedirs(self.labels_dir, exist_ok=True)

    def _get_json_path(self, watch_id: str) -> str:
        """Get path to JSON file for a watch.

        Args:
            watch_id: Watch folder name

        Returns:
            Full path to JSON file
        """
        return os.path.join(self.labels_dir, f"{watch_id}.json")

    def load_annotations(self, watch_id: str) -> dict:
        """Load annotations for a watch.

        Args:
            watch_id: Watch folder name

        Returns:
            Dictionary of annotations keyed by filename, or empty dict if not found
        """
        json_path = self._get_json_path(watch_id)

        if not os.path.exists(json_path):
            return {}

        try:
            with open(json_path, 'r') as f:
                annotations = json.load(f)
            return annotations
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading annotations for {watch_id}: {e}")
            return {}

    def save_annotations(self, watch_id: str, annotations: dict) -> Tuple[bool, str]:
        """Save annotations for a watch.

        Args:
            watch_id: Watch folder name
            annotations: Dictionary of annotations keyed by filename

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        json_path = self._get_json_path(watch_id)

        try:
            with open(json_path, 'w') as f:
                json.dump(annotations, f, indent=2)
            return True, ""
        except IOError as e:
            error_msg = f"Failed to save annotations: {e}"
            print(error_msg)
            return False, error_msg

    def get_image_annotation(self, watch_id: str, filename: str) -> Optional[dict]:
        """Get annotation for a specific image.

        Args:
            watch_id: Watch folder name
            filename: Image filename

        Returns:
            Annotation dict if found, None otherwise
        """
        annotations = self.load_annotations(watch_id)
        return annotations.get(filename)

    def is_image_labeled(self, watch_id: str, filename: str) -> bool:
        """Check if an image has a complete annotation (all 5 keypoints).

        Args:
            watch_id: Watch folder name
            filename: Image filename

        Returns:
            True if all 5 keypoints are present, False otherwise
        """
        annotation = self.get_image_annotation(watch_id, filename)

        if not annotation or "coords_norm" not in annotation:
            return False

        coords = annotation["coords_norm"]
        required_keys = ["top", "left", "right", "bottom", "center"]

        # Check all 5 keypoints are present and have 2 coordinates each
        return all(
            key in coords and
            isinstance(coords[key], list) and
            len(coords[key]) == 2
            for key in required_keys
        )

    def save_image_annotation(
        self,
        watch_id: str,
        filename: str,
        coords_pixel: dict,
        image_size: tuple,
        annotator: str = "unknown"
    ) -> Tuple[bool, str]:
        """Save annotation for an image.

        Args:
            watch_id: Watch folder name
            filename: Image filename
            coords_pixel: Dictionary of pixel coordinates
                         Format: {"top": [x, y], "left": [x, y], ...}
            image_size: Tuple of (width, height) in pixels
            annotator: Annotator identifier (default: "unknown")

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Validate coords_pixel has all 5 keypoints
        required_keys = ["top", "left", "right", "bottom", "center"]
        if not all(key in coords_pixel for key in required_keys):
            return False, "Missing required keypoints"

        # Normalize coordinates to [0, 1] range
        width, height = image_size
        coords_norm = {}

        for key in required_keys:
            x_pixel, y_pixel = coords_pixel[key]
            x_norm = x_pixel / width
            y_norm = y_pixel / height
            coords_norm[key] = [x_norm, y_norm]

        # Create annotation entry
        annotation = {
            "image_size": [width, height],
            "coords_norm": coords_norm,
            "annotator": annotator,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Load existing annotations
        annotations = self.load_annotations(watch_id)

        # Update or insert
        annotations[filename] = annotation

        # Save
        return self.save_annotations(watch_id, annotations)

    def clear_image_annotation(self, watch_id: str, filename: str) -> Tuple[bool, str]:
        """Clear annotation for an image.

        Args:
            watch_id: Watch folder name
            filename: Image filename

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Load annotations
        annotations = self.load_annotations(watch_id)

        # Remove entry if exists
        if filename in annotations:
            del annotations[filename]

        # Save
        return self.save_annotations(watch_id, annotations)

    def filter_images_by_status(
        self,
        images: List[ImageMetadata],
        watch_id: str,
        status_filter: str
    ) -> List[ImageMetadata]:
        """Filter images based on annotation status.

        Args:
            images: List of image metadata
            watch_id: Current watch ID
            status_filter: "all", "unlabeled", or "labeled"

        Returns:
            Filtered list of images
        """
        if status_filter == "all":
            return images

        filtered = []
        for img in images:
            is_labeled = self.is_image_labeled(watch_id, img.filename)

            if status_filter == "unlabeled" and not is_labeled:
                filtered.append(img)
            elif status_filter == "labeled" and is_labeled:
                filtered.append(img)

        return filtered

    def get_annotation_count(self, watch_id: str, filename: str) -> int:
        """Get number of keypoints annotated for an image.

        Args:
            watch_id: Watch folder name
            filename: Image filename

        Returns:
            Number of keypoints (0-5)
        """
        annotation = self.get_image_annotation(watch_id, filename)

        if not annotation or "coords_norm" not in annotation:
            return 0

        coords = annotation["coords_norm"]
        required_keys = ["top", "left", "right", "bottom", "center"]

        # Count how many keypoints are present
        count = sum(
            1 for key in required_keys
            if key in coords and
               isinstance(coords[key], list) and
               len(coords[key]) == 2
        )

        return count
