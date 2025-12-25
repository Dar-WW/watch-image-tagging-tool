"""Pending Changes Manager for batch operations.

Manages pending tag changes and deletions without immediately modifying files.
Changes are only applied when user explicitly saves them.
"""

import json
import os
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from filename_parser import ImageMetadata, generate_filename


@dataclass
class PendingChange:
    """Represents a pending change to an image."""
    original_filename: str
    new_view_type: str
    new_quality: Optional[int]
    watch_id: str


class PendingChangesManager:
    """Manages pending changes to images before they're applied to disk."""

    def __init__(self, persist_file: str = "pending_changes.json"):
        """Initialize the pending changes manager.

        Args:
            persist_file: Optional file path to persist changes across sessions
        """
        self.persist_file = persist_file
        self.pending_tags: Dict[str, PendingChange] = {}  # filename -> PendingChange
        self.pending_deletes: Set[str] = set()  # set of filenames to delete
        self.load_from_disk()

    def add_tag_change(self, image_meta: ImageMetadata, new_view_type: str, new_quality: Optional[int]):
        """Add or update a pending tag change.

        Args:
            image_meta: Current image metadata
            new_view_type: New view type
            new_quality: New quality rating
        """
        change = PendingChange(
            original_filename=image_meta.filename,
            new_view_type=new_view_type,
            new_quality=new_quality,
            watch_id=image_meta.watch_id
        )
        self.pending_tags[image_meta.filename] = change
        self.save_to_disk()

    def add_delete(self, image_meta: ImageMetadata):
        """Mark an image for deletion.

        Args:
            image_meta: Image to delete
        """
        # Remove from pending tags if exists (no point renaming a file we're deleting)
        if image_meta.filename in self.pending_tags:
            del self.pending_tags[image_meta.filename]

        self.pending_deletes.add(image_meta.filename)
        self.save_to_disk()

    def remove_delete(self, filename: str):
        """Unmark an image for deletion.

        Args:
            filename: Filename to undelete
        """
        if filename in self.pending_deletes:
            self.pending_deletes.remove(filename)
            self.save_to_disk()

    def get_pending_state(self, image_meta: ImageMetadata) -> Tuple[str, Optional[int]]:
        """Get the pending view type and quality for an image.

        Args:
            image_meta: Image metadata

        Returns:
            Tuple of (view_type, quality) - uses pending values if they exist,
            otherwise returns current values from image_meta
        """
        if image_meta.filename in self.pending_tags:
            change = self.pending_tags[image_meta.filename]
            return change.new_view_type, change.new_quality
        return image_meta.view_type, image_meta.quality

    def is_pending_delete(self, filename: str) -> bool:
        """Check if an image is marked for deletion.

        Args:
            filename: Filename to check

        Returns:
            True if marked for deletion
        """
        return filename in self.pending_deletes

    def has_changes(self) -> bool:
        """Check if there are any pending changes.

        Returns:
            True if there are pending tags or deletes
        """
        return len(self.pending_tags) > 0 or len(self.pending_deletes) > 0

    def get_changes_count(self) -> Tuple[int, int]:
        """Get count of pending changes.

        Returns:
            Tuple of (tag_changes, deletes)
        """
        return len(self.pending_tags), len(self.pending_deletes)

    def clear_all(self):
        """Clear all pending changes."""
        self.pending_tags.clear()
        self.pending_deletes.clear()
        self.save_to_disk()

    def save_to_disk(self):
        """Persist pending changes to disk."""
        try:
            data = {
                'pending_tags': {
                    filename: asdict(change)
                    for filename, change in self.pending_tags.items()
                },
                'pending_deletes': list(self.pending_deletes)
            }
            with open(self.persist_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            # Silently fail if we can't persist - changes are still in memory
            pass

    def load_from_disk(self):
        """Load pending changes from disk."""
        try:
            if os.path.exists(self.persist_file):
                with open(self.persist_file, 'r') as f:
                    data = json.load(f)

                # Reconstruct pending tags
                self.pending_tags = {
                    filename: PendingChange(**change_data)
                    for filename, change_data in data.get('pending_tags', {}).items()
                }

                # Reconstruct pending deletes
                self.pending_deletes = set(data.get('pending_deletes', []))
        except Exception as e:
            # If load fails, start with empty state
            self.pending_tags.clear()
            self.pending_deletes.clear()

    def apply_changes(self, image_manager) -> Tuple[int, int, List[str]]:
        """Apply all pending changes to disk.

        Args:
            image_manager: ImageManager instance to use for file operations

        Returns:
            Tuple of (successful_renames, successful_deletes, error_messages)
        """
        errors = []
        successful_renames = 0
        successful_deletes = 0

        # First, handle deletions
        for filename in self.pending_deletes:
            # Find the image metadata
            found = False
            for watch_id in image_manager.watches:
                images = image_manager.load_images(watch_id)
                for img in images:
                    if img.filename == filename:
                        success, message = image_manager.delete_image(img)
                        if success:
                            successful_deletes += 1
                        else:
                            errors.append(f"Delete {filename}: {message}")
                        found = True
                        break
                if found:
                    break

        # Then, handle renames (for files that weren't deleted)
        for filename, change in self.pending_tags.items():
            if filename in self.pending_deletes:
                continue  # Skip files that were deleted

            # Find the image metadata
            found = False
            for watch_id in image_manager.watches:
                images = image_manager.load_images(watch_id)
                for img in images:
                    if img.filename == filename:
                        success, message = image_manager.rename_image(
                            img,
                            change.new_view_type,
                            change.new_quality
                        )
                        if success:
                            successful_renames += 1
                        else:
                            errors.append(f"Rename {filename}: {message}")
                        found = True
                        break
                if found:
                    break

            if not found:
                errors.append(f"File not found: {filename}")

        # Clear all changes after applying
        self.clear_all()

        return successful_renames, successful_deletes, errors
