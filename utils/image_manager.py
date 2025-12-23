"""Image manager for watch tagging application.

Handles loading watch folders, images, file operations (rename, delete),
and navigation between watches.
"""

import os
import shutil
from typing import List, Optional, Tuple
from pathlib import Path

try:
    from .filename_parser import ImageMetadata, parse_filename, generate_filename
except ImportError:
    from filename_parser import ImageMetadata, parse_filename, generate_filename


class ImageManager:
    """Manages watch folders, images, and file operations."""

    def __init__(self, images_dir: str = None):
        """Initialize ImageManager.

        Args:
            images_dir: Path to downloaded_images directory. If None, uses ../downloaded_images relative to this file.
        """
        if images_dir is None:
            # Default to downloaded_images in parent directory of this repo
            current_dir = Path(__file__).parent.parent
            images_dir = os.path.join(current_dir, "downloaded_images")

        self.images_dir = images_dir
        self.trash_dir = os.path.join(images_dir, ".trash")
        self.watches: List[str] = []
        self.current_watch_index: int = 0
        self.current_images: List[ImageMetadata] = []

    def load_watches(self) -> List[str]:
        """Scan downloaded_images for watch folders.

        Returns:
            Sorted list of watch folder names
        """
        if not os.path.exists(self.images_dir):
            return []

        # Get all directories, excluding .trash
        watches = []
        for item in os.listdir(self.images_dir):
            item_path = os.path.join(self.images_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                watches.append(item)

        # Sort alphabetically
        watches.sort()
        self.watches = watches
        return watches

    def load_images(self, watch_id: Optional[str] = None) -> List[ImageMetadata]:
        """Load images for a specific watch.

        Args:
            watch_id: Watch folder name. If None, uses current watch.

        Returns:
            List of ImageMetadata for images in the watch folder
        """
        if watch_id is None:
            if not self.watches or self.current_watch_index >= len(self.watches):
                return []
            watch_id = self.watches[self.current_watch_index]

        watch_path = os.path.join(self.images_dir, watch_id)
        if not os.path.exists(watch_path):
            return []

        images = []
        for filename in os.listdir(watch_path):
            if not filename.endswith('.jpg'):
                continue

            filepath = os.path.join(watch_path, filename)
            metadata = parse_filename(filepath)
            if metadata:
                images.append(metadata)

        # Sort by view number
        images.sort(key=lambda x: x.view_number)
        self.current_images = images
        return images

    def rename_image(self, image_meta: ImageMetadata, new_view_type: str, new_quality: Optional[int]) -> Tuple[bool, str]:
        """Rename image file with new tags.

        Args:
            image_meta: Current image metadata
            new_view_type: New view type ("face" or "tiltface")
            new_quality: New quality (1, 2, 3, or None)

        Returns:
            Tuple of (success: bool, message: str)
        """
        old_path = image_meta.full_path

        if not os.path.exists(old_path):
            return False, f"File not found: {old_path}"

        # Create new metadata
        new_meta = ImageMetadata(
            watch_id=image_meta.watch_id,
            view_number=image_meta.view_number,
            view_type=new_view_type,
            quality=new_quality,
            filename="",  # Will be generated
            full_path=""
        )

        # Generate new filename
        new_filename = generate_filename(new_meta)
        new_path = os.path.join(os.path.dirname(old_path), new_filename)

        # Check if file already exists (same name)
        if old_path == new_path:
            return True, "No change needed"

        # Check if target file already exists
        if os.path.exists(new_path):
            return False, f"Target file already exists: {new_filename}"

        # Rename file
        try:
            os.rename(old_path, new_path)
            return True, f"Renamed to {new_filename}"
        except OSError as e:
            return False, f"Failed to rename: {e}"

    def delete_image(self, image_meta: ImageMetadata) -> Tuple[bool, str]:
        """Move image to .trash folder.

        Args:
            image_meta: Image metadata

        Returns:
            Tuple of (success: bool, message: str)
        """
        source = image_meta.full_path

        if not os.path.exists(source):
            return False, f"File not found: {source}"

        # Create trash directory structure
        trash_watch_dir = os.path.join(self.trash_dir, image_meta.watch_id)
        os.makedirs(trash_watch_dir, exist_ok=True)

        # Move file
        dest = os.path.join(trash_watch_dir, image_meta.filename)

        # If dest already exists, add a number suffix
        if os.path.exists(dest):
            base, ext = os.path.splitext(image_meta.filename)
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(trash_watch_dir, f"{base}_{counter}{ext}")
                counter += 1

        try:
            shutil.move(source, dest)
            return True, f"Moved to trash: {image_meta.filename}"
        except OSError as e:
            return False, f"Failed to delete: {e}"

    def next_watch(self) -> Optional[str]:
        """Navigate to next watch.

        Returns:
            Next watch ID, or None if at end
        """
        if not self.watches:
            return None

        if self.current_watch_index < len(self.watches) - 1:
            self.current_watch_index += 1
            return self.watches[self.current_watch_index]

        return None  # Already at last watch

    def prev_watch(self) -> Optional[str]:
        """Navigate to previous watch.

        Returns:
            Previous watch ID, or None if at beginning
        """
        if not self.watches:
            return None

        if self.current_watch_index > 0:
            self.current_watch_index -= 1
            return self.watches[self.current_watch_index]

        return None  # Already at first watch

    def get_current_watch(self) -> Optional[str]:
        """Get current watch ID.

        Returns:
            Current watch ID, or None if no watches
        """
        if not self.watches or self.current_watch_index >= len(self.watches):
            return None
        return self.watches[self.current_watch_index]

    def get_progress(self) -> Tuple[int, int]:
        """Get current progress.

        Returns:
            Tuple of (current_index (1-based), total_watches)
        """
        total = len(self.watches)
        current = self.current_watch_index + 1 if total > 0 else 0
        return current, total

    def set_watch_index(self, index: int) -> bool:
        """Set current watch by index.

        Args:
            index: Watch index (0-based)

        Returns:
            True if successful, False if index out of range
        """
        if 0 <= index < len(self.watches):
            self.current_watch_index = index
            return True
        return False

    def load_trash_images(self) -> dict:
        """Load all deleted images from trash, organized by watch.

        Returns:
            Dictionary mapping watch_id to list of (ImageMetadata, deleted_time) tuples
        """
        trash_images = {}

        if not os.path.exists(self.trash_dir):
            return trash_images

        for watch_id in os.listdir(self.trash_dir):
            trash_watch_dir = os.path.join(self.trash_dir, watch_id)

            if not os.path.isdir(trash_watch_dir):
                continue

            images = []
            for filename in os.listdir(trash_watch_dir):
                if not filename.endswith('.jpg'):
                    continue

                filepath = os.path.join(trash_watch_dir, filename)
                metadata = parse_filename(filepath)

                if metadata:
                    # Get file modification time (when it was deleted)
                    deleted_time = os.path.getmtime(filepath)
                    images.append((metadata, deleted_time))

            if images:
                # Sort by deletion time, most recent first
                images.sort(key=lambda x: x[1], reverse=True)
                trash_images[watch_id] = images

        return trash_images

    def restore_image(self, image_meta: ImageMetadata) -> Tuple[bool, str]:
        """Restore a deleted image from trash back to its original location.

        Args:
            image_meta: Image metadata (should point to trash location)

        Returns:
            Tuple of (success: bool, message: str)
        """
        trash_path = image_meta.full_path

        if not os.path.exists(trash_path):
            return False, f"File not found in trash: {trash_path}"

        # Determine original location
        watch_dir = os.path.join(self.images_dir, image_meta.watch_id)
        dest_path = os.path.join(watch_dir, image_meta.filename)

        # Check if destination already exists
        if os.path.exists(dest_path):
            return False, f"File already exists at destination: {image_meta.filename}"

        # Ensure watch directory exists
        os.makedirs(watch_dir, exist_ok=True)

        try:
            shutil.move(trash_path, dest_path)
            return True, f"Restored: {image_meta.filename}"
        except OSError as e:
            return False, f"Failed to restore: {e}"
