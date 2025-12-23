"""Hashing utilities for cache key generation."""

import hashlib
import json
from pathlib import Path
from typing import Dict, Any


def hash_file(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to file
        chunk_size: Size of chunks to read (bytes)

    Returns:
        str: Hexadecimal hash string

    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file can't be read
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)

    return sha256.hexdigest()


def hash_config(config: Dict[str, Any]) -> str:
    """Compute hash of configuration dictionary.

    Args:
        config: Configuration dictionary

    Returns:
        str: Hexadecimal hash string
    """
    # Convert to stable JSON string (sorted keys)
    config_str = json.dumps(config, sort_keys=True, separators=(",", ":"))

    # Compute SHA256
    sha256 = hashlib.sha256()
    sha256.update(config_str.encode("utf-8"))

    return sha256.hexdigest()


def hash_string(text: str) -> str:
    """Compute SHA256 hash of a string.

    Args:
        text: Input string

    Returns:
        str: Hexadecimal hash string
    """
    sha256 = hashlib.sha256()
    sha256.update(text.encode("utf-8"))
    return sha256.hexdigest()
