"""Template annotation manager for watch templates.

Handles loading, saving, and managing template keypoint annotations.
Template annotations are stored in templates/{template_name}/annotations.json
with the same normalized coordinate format as image annotations.
"""

import os
import json
from typing import Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone


class TemplateManager:
    """Manages template annotations for watch templates."""

    def __init__(self, templates_dir: str = None):
        """Initialize TemplateManager.

        Args:
            templates_dir: Path to templates directory.
                          If None, uses ../templates relative to this file.
        """
        if templates_dir is None:
            # Default to templates in parent directory of this repo
            current_dir = Path(__file__).parent.parent
            templates_dir = os.path.join(current_dir, "templates")

        self.templates_dir = templates_dir

    def get_template_path(self, template_name: str) -> str:
        """Get path to template image file.

        Args:
            template_name: Template name (e.g., "nab")

        Returns:
            Full path to template.jpeg
        """
        return os.path.join(self.templates_dir, template_name, "template.jpeg")

    def _get_annotations_path(self, template_name: str) -> str:
        """Get path to annotations.json for a template.

        Args:
            template_name: Template name

        Returns:
            Full path to annotations.json
        """
        return os.path.join(self.templates_dir, template_name, "annotations.json")

    def load_template_annotations(self, template_name: str) -> Optional[dict]:
        """Load annotations for a template.

        Args:
            template_name: Template name (e.g., "nab")

        Returns:
            Annotation dictionary if found, None otherwise
            Format matches AlignmentManager: {
                "image_size": [width, height],
                "coords_norm": {
                    "top": [x, y],
                    "left": [x, y],
                    "right": [x, y],
                    "bottom": [x, y],
                    "center": [x, y]
                },
                "annotator": str,
                "timestamp": str
            }
        """
        json_path = self._get_annotations_path(template_name)

        if not os.path.exists(json_path):
            return None

        try:
            with open(json_path, 'r') as f:
                annotation = json.load(f)
            return annotation
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading template annotations for {template_name}: {e}")
            return None

    def save_template_annotations(
        self,
        template_name: str,
        coords_pixel: dict,
        image_size: tuple,
        annotator: str = "unknown"
    ) -> Tuple[bool, str]:
        """Save annotations for a template.

        Args:
            template_name: Template name
            coords_pixel: Dictionary of pixel coordinates
                         Format: {"top": [x, y], "left": [x, y], ...}
            image_size: Tuple of (width, height) in pixels
            annotator: Annotator identifier

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

        # Ensure directory exists
        template_dir = os.path.join(self.templates_dir, template_name)
        os.makedirs(template_dir, exist_ok=True)

        # Save
        json_path = self._get_annotations_path(template_name)
        try:
            with open(json_path, 'w') as f:
                json.dump(annotation, f, indent=2)
            return True, ""
        except IOError as e:
            error_msg = f"Failed to save template annotations: {e}"
            print(error_msg)
            return False, error_msg

    def is_template_labeled(self, template_name: str) -> bool:
        """Check if template has complete annotation (all 5 keypoints).

        Args:
            template_name: Template name

        Returns:
            True if all 5 keypoints are present, False otherwise
        """
        annotation = self.load_template_annotations(template_name)

        if not annotation or "coords_norm" not in annotation:
            return False

        coords = annotation["coords_norm"]
        required_keys = ["top", "left", "right", "bottom", "center"]

        return all(
            key in coords and
            isinstance(coords[key], list) and
            len(coords[key]) == 2
            for key in required_keys
        )

    def clear_template_annotations(self, template_name: str) -> Tuple[bool, str]:
        """Clear annotations for a template.

        Args:
            template_name: Template name

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        json_path = self._get_annotations_path(template_name)

        if os.path.exists(json_path):
            try:
                os.remove(json_path)
                return True, "Template annotations cleared"
            except OSError as e:
                return False, f"Failed to clear annotations: {e}"

        return True, "No annotations to clear"
