"""Resolve Label Studio image paths to local filesystem paths."""

from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Optional


class PathResolver:
    """Resolve Label Studio image URLs to local file paths.

    Handles conversion between Label Studio's URL format and actual
    filesystem paths in both Docker and local development environments.
    """

    def __init__(self, media_mount: str, local_media: str):
        """Initialize path resolver.

        Args:
            media_mount: Docker media mount point (e.g., /label-studio/media)
            local_media: Local media directory (e.g., ../downloaded_images)
        """
        self.media_mount = Path(media_mount)
        self.local_media = Path(local_media)

    def resolve(self, label_studio_path: str) -> Optional[Path]:
        """Resolve Label Studio image path to local filesystem path.

        Handles multiple formats:
        - /data/local-files/?d=images/PATEK_nab_001/image.jpg
        - /data/media/image.jpg
        - Absolute file paths

        Args:
            label_studio_path: Image path from Label Studio task

        Returns:
            Path: Resolved local file path, or None if invalid
        """
        # Handle Label Studio local-files URL format
        if "/data/local-files/" in label_studio_path:
            return self._resolve_local_files_url(label_studio_path)

        # Handle direct media path
        if label_studio_path.startswith("/data/media/"):
            relative_path = label_studio_path.replace("/data/media/", "")
            return self.media_mount / relative_path

        # Handle absolute paths (for local development)
        path = Path(label_studio_path)
        if path.is_absolute() and path.exists():
            return path

        # Try as relative path from local_media
        potential_path = self.local_media / label_studio_path
        if potential_path.exists():
            return potential_path

        return None

    def _resolve_local_files_url(self, url: str) -> Optional[Path]:
        """Resolve Label Studio local-files URL format.

        Example:
            /data/local-files/?d=images/PATEK_nab_001/image.jpg
            -> {media_mount}/images/PATEK_nab_001/image.jpg

        Args:
            url: Label Studio local-files URL

        Returns:
            Path: Resolved path or None
        """
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            # Extract 'd' parameter (file path)
            if "d" not in query_params:
                return None

            relative_path = query_params["d"][0]

            # Try media mount path (Docker)
            media_path = self.media_mount / relative_path
            if media_path.exists():
                return media_path

            # Try local media path (development)
            local_path = self.local_media / relative_path
            if local_path.exists():
                return local_path

            return None

        except Exception:
            return None

    def validate_path(self, path: Path) -> bool:
        """Validate that path exists and is a file.

        Args:
            path: Path to validate

        Returns:
            bool: True if valid file path
        """
        return path is not None and path.exists() and path.is_file()
