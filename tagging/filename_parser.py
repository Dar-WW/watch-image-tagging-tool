"""Filename parser for watch image tagging.

Handles parsing and generating filenames with the format:
{WATCH_ID}_{VIEW_NUM}_{VIEW_TYPE}_q{QUALITY}.jpg

Examples:
    - PATEK_nab_042_04_face_q3.jpg (face view, quality 3)
    - PATEK_nab_049_06_tiltface_q2.jpg (tiltface view, quality 2)
    - PATEK_nab_001_03_face.jpg (legacy format without quality)
"""

import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageMetadata:
    """Metadata extracted from image filename."""
    watch_id: str          # e.g., "PATEK_nab_042"
    view_number: str       # e.g., "04" (keep as string to preserve leading zero)
    view_type: str         # "face" or "tiltface"
    quality: Optional[int] # 1, 2, 3, or None
    filename: str          # Original filename
    full_path: str         # Full path to the file


def parse_filename(filepath: str) -> Optional[ImageMetadata]:
    """Parse filename to extract metadata.

    Args:
        filepath: Full path to the image file

    Returns:
        ImageMetadata if filename matches expected pattern, None otherwise
    """
    filename = os.path.basename(filepath)

    # Pattern with quality tag: PATEK_nab_042_04_face_q3.jpg
    pattern_tagged = r'^(.+?)_(\d{2})_(face|tiltface)_q([123])\.jpg$'
    match = re.match(pattern_tagged, filename)

    if match:
        return ImageMetadata(
            watch_id=match.group(1),
            view_number=match.group(2),
            view_type=match.group(3),
            quality=int(match.group(4)),
            filename=filename,
            full_path=filepath
        )

    # Pattern without quality tag (legacy): PATEK_nab_042_04_face.jpg
    pattern_legacy = r'^(.+?)_(\d{2})_(face|tiltface)\.jpg$'
    match = re.match(pattern_legacy, filename)

    if match:
        return ImageMetadata(
            watch_id=match.group(1),
            view_number=match.group(2),
            view_type=match.group(3),
            quality=None,
            filename=filename,
            full_path=filepath
        )

    return None  # Malformed filename


def generate_filename(metadata: ImageMetadata) -> str:
    """Generate filename from metadata.

    Args:
        metadata: Image metadata

    Returns:
        Filename string with tags
    """
    base = f"{metadata.watch_id}_{metadata.view_number}_{metadata.view_type}"

    if metadata.quality is not None:
        return f"{base}_q{metadata.quality}.jpg"
    else:
        return f"{base}.jpg"


def extract_watch_id(filename: str) -> Optional[str]:
    """Extract watch ID from filename.

    Args:
        filename: Image filename

    Returns:
        Watch ID if found, None otherwise
    """
    pattern = r'^(.+?)_\d{2}_'
    match = re.match(pattern, filename)
    return match.group(1) if match else None
