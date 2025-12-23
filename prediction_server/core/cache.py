"""Disk-based prediction caching system."""

import json
from pathlib import Path
from typing import Optional, Dict, Any


class PredictionCache:
    """Filesystem-based cache for prediction results.

    Caches predictions to disk using JSON serialization.
    Cache keys are generated from image hash + pipeline version + config hash.
    """

    def __init__(self, cache_dir: Path, enabled: bool = True):
        """Initialize cache.

        Args:
            cache_dir: Directory for cache files
            enabled: Whether caching is enabled
        """
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Load cached prediction.

        Args:
            key: Cache key

        Returns:
            dict: Cached prediction data, or None if not found
        """
        if not self.enabled:
            return None

        cache_file = self._get_cache_path(key)

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load cache for {key}: {e}")
            return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        """Save prediction to cache.

        Args:
            key: Cache key
            value: Prediction data to cache
        """
        if not self.enabled:
            return

        cache_file = self._get_cache_path(key)

        try:
            with open(cache_file, "w") as f:
                json.dump(value, f, indent=2)
        except IOError as e:
            print(f"Warning: Failed to save cache for {key}: {e}")

    def make_key(
        self, image_hash: str, pipeline_version: str, config_hash: str
    ) -> str:
        """Generate cache key from inputs.

        Args:
            image_hash: Hash of the image file
            pipeline_version: Version string of the pipeline
            config_hash: Hash of the pipeline configuration

        Returns:
            str: Cache key
        """
        return f"{image_hash}_{pipeline_version}_{config_hash}"

    def _get_cache_path(self, key: str) -> Path:
        """Get full path to cache file.

        Args:
            key: Cache key

        Returns:
            Path: Full path to cache file
        """
        return self.cache_dir / f"{key}.json"

    def clear(self) -> int:
        """Clear all cached predictions.

        Returns:
            int: Number of cache files deleted
        """
        if not self.enabled or not self.cache_dir.exists():
            return 0

        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except OSError:
                pass

        return count

    def size(self) -> int:
        """Get number of cached predictions.

        Returns:
            int: Number of cache files
        """
        if not self.enabled or not self.cache_dir.exists():
            return 0

        return len(list(self.cache_dir.glob("*.json")))
