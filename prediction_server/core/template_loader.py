"""Template loader for watch keypoint annotations and images."""

import json
from pathlib import Path
from typing import Dict, Tuple
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class TemplateData:
    """Container for template data."""
    keypoints_norm: Dict[str, Tuple[float, float]]  # Normalized [0, 1] coordinates
    template_image: np.ndarray  # BGR image
    image_size: Tuple[int, int]  # (width, height)
    model_name: str


class TemplateLoader:
    """
    Loader for watch template keypoints and images.

    Templates are stored in the following structure:
    templates/
      └── {model_name}/
          ├── annotations.json  # Keypoint coordinates
          └── template.jpeg     # Reference image
    """

    def __init__(self, templates_dir: Path):
        """
        Initialize template loader.

        Args:
            templates_dir: Path to templates directory
        """
        self.templates_dir = Path(templates_dir)
        if not self.templates_dir.exists():
            raise FileNotFoundError(f"Templates directory not found: {templates_dir}")

    def load_template(self, model_name: str = "nab") -> TemplateData:
        """
        Load template keypoints and image for a watch model.

        Args:
            model_name: Model identifier (e.g., "nab" for Nautilus)

        Returns:
            TemplateData with keypoints and image

        Raises:
            FileNotFoundError: If template files don't exist
            ValueError: If template format is invalid
        """
        model_dir = self.templates_dir / model_name

        if not model_dir.exists():
            raise FileNotFoundError(
                f"Template directory not found: {model_dir}. "
                f"Available templates: {self._list_available_templates()}"
            )

        # Load annotations.json
        annotations_path = model_dir / "annotations.json"
        if not annotations_path.exists():
            raise FileNotFoundError(f"Annotations file not found: {annotations_path}")

        with open(annotations_path, 'r') as f:
            annotations = json.load(f)

        # Validate format
        if "image_size" not in annotations:
            raise ValueError(f"Missing 'image_size' in {annotations_path}")
        if "coords_norm" not in annotations:
            raise ValueError(f"Missing 'coords_norm' in {annotations_path}")

        image_size = tuple(annotations["image_size"])  # [width, height]
        coords_norm = annotations["coords_norm"]

        # Validate required keypoints
        required_kps = {"top", "bottom", "left", "right", "center"}
        missing_kps = required_kps - set(coords_norm.keys())
        if missing_kps:
            raise ValueError(
                f"Missing required keypoints in {annotations_path}: {missing_kps}"
            )

        # Convert lists to tuples
        keypoints_norm = {
            name: tuple(coords) for name, coords in coords_norm.items()
        }

        # Load template image
        template_image_path = model_dir / "template.jpeg"
        if not template_image_path.exists():
            # Try .jpg extension
            template_image_path = model_dir / "template.jpg"
            if not template_image_path.exists():
                raise FileNotFoundError(
                    f"Template image not found: {model_dir}/template.jpeg or template.jpg"
                )

        template_image = cv2.imread(str(template_image_path))
        if template_image is None:
            raise ValueError(f"Failed to load template image: {template_image_path}")

        return TemplateData(
            keypoints_norm=keypoints_norm,
            template_image=template_image,
            image_size=image_size,
            model_name=model_name
        )

    def _list_available_templates(self) -> str:
        """List available template names."""
        try:
            templates = [
                d.name for d in self.templates_dir.iterdir()
                if d.is_dir() and (d / "annotations.json").exists()
            ]
            return ", ".join(templates) if templates else "none"
        except Exception:
            return "unknown"
