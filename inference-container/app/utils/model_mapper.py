"""
Model Mapper Utility

Maps watch IDs to their corresponding template models for keypoint prediction.
This module automatically detects available templates from the templates/ directory,
so adding a new template is as simple as creating a new template directory with
template.jpeg and annotations.json files.

Examples:
    PATEK_nab_042 -> "nab" (Nautilus)
    PATEK_nam_001 -> "nam" (Nautilus Moonphase)
    CARTIER_sant_001 -> "sant" (Santos)
"""

import re
from pathlib import Path
from typing import Optional


# Default template to use if model cannot be determined
DEFAULT_TEMPLATE = "nab"

# Cache for template directory
_TEMPLATES_DIR = None


def _get_templates_dir() -> Path:
    """Get the templates directory path (cached)."""
    global _TEMPLATES_DIR
    if _TEMPLATES_DIR is None:
        # This file is in utils/, templates/ is at the project root
        _TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
    return _TEMPLATES_DIR


def template_exists(template_name: str) -> bool:
    """
    Check if a template directory exists with required files.

    Args:
        template_name: Name of the template directory

    Returns:
        True if template directory exists with template.jpeg file

    Examples:
        >>> template_exists("nab")
        True
        >>> template_exists("nonexistent")
        False
    """
    templates_dir = _get_templates_dir()
    template_dir = templates_dir / template_name

    if not template_dir.exists() or not template_dir.is_dir():
        return False

    # Check for required template.jpeg file
    template_file = template_dir / "template.jpeg"
    return template_file.exists()


def extract_model_identifier(watch_id: str) -> Optional[str]:
    """
    Extract the model identifier from a watch ID.

    Args:
        watch_id: Watch ID string (e.g., "PATEK_nab_042", "PATEK_nam_001")

    Returns:
        Model identifier (e.g., "nab", "nam") or None if not found

    Examples:
        >>> extract_model_identifier("PATEK_nab_042")
        "nab"
        >>> extract_model_identifier("PATEK_nam_001")
        "nam"
        >>> extract_model_identifier("CARTIER_sant_001")
        "sant"
    """
    # Pattern: BRAND_model_number
    # Captures the model identifier (letters/numbers between first and second underscore)
    pattern = r'^[A-Z]+_([a-z0-9]+)_\d+'
    match = re.match(pattern, watch_id)

    if match:
        return match.group(1)
    return None


def get_template_for_watch_id(watch_id: str) -> str:
    """
    Map a watch ID to its corresponding template model name.

    This function extracts the model identifier from the watch ID and checks
    if a template directory exists for it. If found, returns the model identifier
    as the template name. Otherwise, returns the default template.

    Args:
        watch_id: Watch ID string (e.g., "PATEK_nab_042", "CARTIER_sant_001")

    Returns:
        Template name to use for this watch model

    Examples:
        >>> get_template_for_watch_id("PATEK_nab_042")
        "nab"
        >>> get_template_for_watch_id("CARTIER_sant_001")
        "sant"
        >>> get_template_for_watch_id("UNKNOWN_xyz_999")
        "nab"  # Returns default
    """
    model_id = extract_model_identifier(watch_id)

    # If model_id exists and has a corresponding template directory, use it
    if model_id and template_exists(model_id):
        return model_id

    # Return default if model not recognized or template doesn't exist
    return DEFAULT_TEMPLATE


def get_template_from_filename(filename: str) -> str:
    """
    Extract template name from an image filename.

    Convenience function that extracts the watch ID from a filename and
    returns the appropriate template name.

    Args:
        filename: Image filename (e.g., "PATEK_nab_042_04_face_q3.jpg")

    Returns:
        Template name to use for this image

    Examples:
        >>> get_template_from_filename("PATEK_nab_042_04_face_q3.jpg")
        "nab"
        >>> get_template_from_filename("CARTIER_sant_001_01_face_q2.jpg")
        "sant"
    """
    # Import here to avoid circular dependency
    try:
        from .filename_parser import extract_watch_id
    except ImportError:
        from filename_parser import extract_watch_id

    watch_id = extract_watch_id(filename)

    if watch_id:
        return get_template_for_watch_id(watch_id)

    return DEFAULT_TEMPLATE


def get_supported_models() -> list:
    """
    Get a list of all available template models by scanning the templates directory.

    Returns:
        List of template names that have valid template directories

    Examples:
        >>> get_supported_models()
        ["nab", "nam", "sant", "datj", ...]
    """
    templates_dir = _get_templates_dir()

    if not templates_dir.exists():
        return []

    supported = []
    for item in templates_dir.iterdir():
        if item.is_dir() and template_exists(item.name):
            supported.append(item.name)

    return sorted(supported)
