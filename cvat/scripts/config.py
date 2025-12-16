"""Configuration for CVAT scripts."""

import os
from pathlib import Path

# Base paths
SCRIPT_DIR = Path(__file__).parent
CVAT_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = CVAT_DIR.parent

# Data directories
IMAGES_DIR = PROJECT_ROOT / "downloaded_images"
ALIGNMENT_LABELS_DIR = PROJECT_ROOT / "alignment_labels"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# CVAT configuration
CVAT_HOST = os.environ.get("CVAT_HOST", "http://localhost:8080")
CVAT_USERNAME = os.environ.get("CVAT_USERNAME", "admin")
CVAT_PASSWORD = os.environ.get("CVAT_PASSWORD", "")

# Label schema
LABEL_NAME = "watch_landmarks"
KEYPOINT_ORDER = ["top", "bottom", "left", "right", "center"]

# Mapping between internal quality codes and CVAT attribute values
QUALITY_MAP = {
    1: "bad",
    2: "partial",
    3: "full"
}

QUALITY_REVERSE_MAP = {v: k for k, v in QUALITY_MAP.items()}

# View type mapping (internal uses same names as CVAT)
VIEW_TYPES = ["face", "tiltface"]
