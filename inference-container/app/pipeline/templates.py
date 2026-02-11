"""Template validation helpers for the inference container."""

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# Resolved at module level - templates are baked into the container
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def get_available_templates() -> List[str]:
    """Get list of available template model names.

    Returns:
        Sorted list of template names that have required files.
    """
    if not _TEMPLATES_DIR.exists():
        logger.warning(f"Templates directory not found: {_TEMPLATES_DIR}")
        return []

    templates = []
    for item in _TEMPLATES_DIR.iterdir():
        if item.is_dir() and (item / "annotations.json").exists() and (
            (item / "template.jpeg").exists() or (item / "template.jpg").exists()
        ):
            templates.append(item.name)

    return sorted(templates)


def validate_template(template_name: str) -> bool:
    """Check if a template exists and has required files.

    Args:
        template_name: Template model name (e.g., "nab").

    Returns:
        True if template is valid and usable.
    """
    template_dir = _TEMPLATES_DIR / template_name
    if not template_dir.exists():
        return False

    has_annotations = (template_dir / "annotations.json").exists()
    has_image = (
        (template_dir / "template.jpeg").exists()
        or (template_dir / "template.jpg").exists()
    )

    return has_annotations and has_image
