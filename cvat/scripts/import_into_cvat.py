#!/usr/bin/env python3
"""Import annotations into CVAT via API.

This script creates tasks in CVAT and imports annotations using the CVAT REST API.

Usage:
    python import_into_cvat.py --watch WATCH_ID
    python import_into_cvat.py --all
    
Prerequisites:
    - CVAT running locally (./run_cvat_local.sh start)
    - Environment variables set: CVAT_USERNAME, CVAT_PASSWORD
    - Or pass credentials via --username and --password
"""

import argparse
import json
import os
import sys
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cvat.scripts.config import (
    CVAT_HOST, CVAT_USERNAME, CVAT_PASSWORD,
    IMAGES_DIR, ALIGNMENT_LABELS_DIR, KEYPOINT_ORDER,
    LABEL_NAME, QUALITY_MAP
)


class CVATClient:
    """Simple CVAT API client."""
    
    def __init__(self, host: str, username: str, password: str):
        self.host = host.rstrip('/')
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.org = ""
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with CVAT."""
        # Login
        login_url = f"{self.host}/api/auth/login"
        response = self.session.post(
            login_url,
            json={"username": self.username, "password": self.password}
        )
        
        if response.status_code != 200:
            raise Exception(f"Authentication failed: {response.text}")
        
        # Get CSRF token
        self.session.headers.update({
            'X-CSRFToken': self.session.cookies.get('csrftoken', '')
        })
        
        print(f"Authenticated as {self.username}")
    
    def create_project(self, name: str, labels: List[Dict]) -> int:
        """Create a project with the given labels.
        
        Args:
            name: Project name
            labels: List of label definitions
            
        Returns:
            Project ID
        """
        url = f"{self.host}/api/projects"
        data = {
            "name": name,
            "labels": labels
        }
        
        response = self.session.post(url, json=data)
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create project: {response.text}")
        
        project_id = response.json()["id"]
        print(f"Created project: {name} (ID: {project_id})")
        return project_id
    
    def get_or_create_project(self, name: str, labels: List[Dict]) -> int:
        """Get existing project or create new one.
        
        Args:
            name: Project name
            labels: List of label definitions
            
        Returns:
            Project ID
        """
        # Search for existing project
        url = f"{self.host}/api/projects"
        response = self.session.get(url, params={"search": name})
        
        if response.status_code == 200:
            results = response.json().get("results", [])
            for project in results:
                if project["name"] == name:
                    print(f"Found existing project: {name} (ID: {project['id']})")
                    return project["id"]
        
        # Create new project
        return self.create_project(name, labels)
    
    def create_task(self, name: str, project_id: int) -> int:
        """Create a task within a project.
        
        Args:
            name: Task name
            project_id: Parent project ID
            
        Returns:
            Task ID
        """
        url = f"{self.host}/api/tasks"
        data = {
            "name": name,
            "project_id": project_id
        }
        
        response = self.session.post(url, json=data)
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create task: {response.text}")
        
        task_id = response.json()["id"]
        print(f"Created task: {name} (ID: {task_id})")
        return task_id
    
    def upload_images_from_share(self, task_id: int, share_path: str) -> bool:
        """Upload images to task from shared directory.
        
        Args:
            task_id: Task ID
            share_path: Path relative to CVAT share directory
            
        Returns:
            True if successful
        """
        url = f"{self.host}/api/tasks/{task_id}/data"
        data = {
            "image_quality": 100,
            "use_zip_chunks": True,
            "use_cache": True,
            "server_files": [share_path],
            "server_files_type": "dir"
        }
        
        response = self.session.post(url, json=data)
        
        if response.status_code not in [200, 201, 202]:
            raise Exception(f"Failed to upload images: {response.text}")
        
        # Wait for upload to complete
        print(f"Uploading images from share:/{share_path}...")
        return self._wait_for_task_data(task_id)
    
    def upload_images_from_local(self, task_id: int, image_paths: List[Path]) -> bool:
        """Upload images to task from local filesystem.
        
        Args:
            task_id: Task ID
            image_paths: List of local image file paths
            
        Returns:
            True if successful
        """
        url = f"{self.host}/api/tasks/{task_id}/data"
        
        files = []
        for i, path in enumerate(image_paths):
            files.append(('client_files[%d]' % i, (path.name, open(path, 'rb'), 'image/jpeg')))
        
        data = {
            "image_quality": 100,
        }
        
        response = self.session.post(url, files=files, data=data)
        
        # Close file handles
        for _, (_, fh, _) in files:
            fh.close()
        
        if response.status_code not in [200, 201, 202]:
            raise Exception(f"Failed to upload images: {response.text}")
        
        print(f"Uploading {len(image_paths)} images...")
        return self._wait_for_task_data(task_id)
    
    def _wait_for_task_data(self, task_id: int, timeout: int = 300) -> bool:
        """Wait for task data upload to complete.
        
        Args:
            task_id: Task ID
            timeout: Maximum wait time in seconds
            
        Returns:
            True if successful
        """
        url = f"{self.host}/api/tasks/{task_id}/status"
        start = time.time()
        
        while time.time() - start < timeout:
            response = self.session.get(url)
            
            if response.status_code == 200:
                status = response.json()
                state = status.get("state", "")
                
                if state == "Finished":
                    print("Upload complete")
                    return True
                elif state == "Failed":
                    print(f"Upload failed: {status.get('message', 'Unknown error')}")
                    return False
                
                print(f"Upload status: {state} ({status.get('progress', 0):.0%})")
            
            time.sleep(2)
        
        print("Upload timed out")
        return False
    
    def import_annotations(self, task_id: int, xml_path: Path) -> bool:
        """Import annotations from CVAT XML file.
        
        Args:
            task_id: Task ID
            xml_path: Path to CVAT XML annotation file
            
        Returns:
            True if successful
        """
        url = f"{self.host}/api/tasks/{task_id}/annotations"
        
        with open(xml_path, 'rb') as f:
            files = {'annotation_file': (xml_path.name, f, 'text/xml')}
            params = {'format': 'CVAT for images 1.1'}
            
            response = self.session.put(url, files=files, params=params)
        
        if response.status_code not in [200, 201, 202]:
            raise Exception(f"Failed to import annotations: {response.text}")
        
        print(f"Imported annotations from {xml_path.name}")
        return True
    
    def get_task_frames(self, task_id: int) -> List[Dict]:
        """Get list of frames/images in a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of frame info dictionaries
        """
        url = f"{self.host}/api/tasks/{task_id}/data/meta"
        response = self.session.get(url)
        
        if response.status_code != 200:
            return []
        
        return response.json().get("frames", [])


def get_project_labels() -> List[Dict]:
    """Get label schema for the project."""
    return [
        {
            "name": LABEL_NAME,
            "type": "skeleton",
            "color": "#FF5733",
            "attributes": [
                {
                    "name": "quality",
                    "mutable": False,
                    "input_type": "select",
                    "default_value": "full",
                    "values": ["bad", "partial", "full"]
                },
                {
                    "name": "view_type",
                    "mutable": False,
                    "input_type": "select",
                    "default_value": "face",
                    "values": ["face", "tiltface"]
                }
            ],
            "sublabels": [
                {"name": keypoint, "type": "points"}
                for keypoint in KEYPOINT_ORDER
            ]
        },
        {
            "name": "crop_roi",
            "type": "rectangle",
            "color": "#33FF57",
            "attributes": [
                {
                    "name": "crop_type",
                    "mutable": False,
                    "input_type": "select",
                    "default_value": "watch_face",
                    "values": ["watch_face", "dial", "custom"]
                }
            ]
        }
    ]


def get_watch_images(watch_id: str) -> List[Path]:
    """Get list of images for a watch."""
    watch_dir = IMAGES_DIR / watch_id
    
    if not watch_dir.exists():
        return []
    
    return sorted(watch_dir.glob("*.jpg"))


def import_watch(
    client: CVATClient,
    watch_id: str,
    project_id: int,
    annotations_dir: Optional[Path] = None,
    use_share: bool = True
) -> Optional[int]:
    """Import a watch folder into CVAT.
    
    Args:
        client: CVAT API client
        watch_id: Watch folder name
        project_id: Project ID
        annotations_dir: Directory containing CVAT XML files (optional)
        use_share: Use shared directory (True) or upload files (False)
        
    Returns:
        Task ID if successful, None otherwise
    """
    print(f"\nImporting {watch_id}...")
    
    # Check for images
    images = get_watch_images(watch_id)
    if not images:
        print(f"  No images found for {watch_id}")
        return None
    
    print(f"  Found {len(images)} images")
    
    # Create task
    try:
        task_id = client.create_task(watch_id, project_id)
    except Exception as e:
        print(f"  Failed to create task: {e}")
        return None
    
    # Upload images
    try:
        if use_share:
            # Use shared directory
            success = client.upload_images_from_share(task_id, watch_id)
        else:
            # Upload from local filesystem
            success = client.upload_images_from_local(task_id, images)
        
        if not success:
            print(f"  Image upload failed")
            return None
    except Exception as e:
        print(f"  Failed to upload images: {e}")
        return None
    
    # Import annotations if available
    if annotations_dir:
        annotation_file = annotations_dir / f"{watch_id}_annotations.xml"
        if annotation_file.exists():
            try:
                client.import_annotations(task_id, annotation_file)
            except Exception as e:
                print(f"  Warning: Failed to import annotations: {e}")
    
    return task_id


def get_all_watch_ids() -> List[str]:
    """Get list of all watch IDs."""
    if not IMAGES_DIR.exists():
        return []
    
    watch_ids = []
    for d in IMAGES_DIR.iterdir():
        if d.is_dir() and not d.name.startswith('.'):
            watch_ids.append(d.name)
    
    return sorted(watch_ids)


def main():
    parser = argparse.ArgumentParser(
        description="Import annotations into CVAT via API"
    )
    parser.add_argument(
        "--watch",
        type=str,
        help="Watch ID to import (e.g., PATEK_nab_001)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Import all watches"
    )
    parser.add_argument(
        "--project",
        type=str,
        default="Watch Annotations",
        help="CVAT project name"
    )
    parser.add_argument(
        "--annotations-dir",
        type=str,
        help="Directory containing CVAT XML annotation files"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=CVAT_HOST,
        help="CVAT host URL"
    )
    parser.add_argument(
        "--username",
        type=str,
        default=CVAT_USERNAME,
        help="CVAT username"
    )
    parser.add_argument(
        "--password",
        type=str,
        default=CVAT_PASSWORD,
        help="CVAT password"
    )
    parser.add_argument(
        "--upload-files",
        action="store_true",
        help="Upload files instead of using shared directory"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all watch folders"
    )
    
    args = parser.parse_args()
    
    # List watches
    if args.list:
        watch_ids = get_all_watch_ids()
        print(f"Found {len(watch_ids)} watch folders:")
        for watch_id in watch_ids:
            images = get_watch_images(watch_id)
            print(f"  - {watch_id} ({len(images)} images)")
        return
    
    # Check credentials
    if not args.password:
        print("Error: CVAT password required. Set CVAT_PASSWORD or use --password")
        sys.exit(1)
    
    # Initialize client
    try:
        client = CVATClient(args.host, args.username, args.password)
    except Exception as e:
        print(f"Failed to connect to CVAT: {e}")
        sys.exit(1)
    
    # Get or create project
    labels = get_project_labels()
    project_id = client.get_or_create_project(args.project, labels)
    
    # Annotations directory
    annotations_dir = Path(args.annotations_dir) if args.annotations_dir else None
    
    # Import specific watch
    if args.watch:
        task_id = import_watch(
            client, args.watch, project_id,
            annotations_dir, not args.upload_files
        )
        sys.exit(0 if task_id else 1)
    
    # Import all watches
    if args.all:
        watch_ids = get_all_watch_ids()
        
        if not watch_ids:
            print("No watch folders found")
            sys.exit(1)
        
        print(f"Importing {len(watch_ids)} watches...")
        
        success_count = 0
        for watch_id in watch_ids:
            task_id = import_watch(
                client, watch_id, project_id,
                annotations_dir, not args.upload_files
            )
            if task_id:
                success_count += 1
        
        print(f"\nImported {success_count}/{len(watch_ids)} watches")
        sys.exit(0 if success_count > 0 else 1)
    
    parser.print_help()


if __name__ == "__main__":
    main()
