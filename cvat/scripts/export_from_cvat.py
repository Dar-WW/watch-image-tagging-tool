#!/usr/bin/env python3
"""Export annotations from CVAT via API.

This script exports annotations from CVAT tasks to the CVAT XML format,
which can then be converted to our internal format.

Usage:
    python export_from_cvat.py --task TASK_ID --output exported.xml
    python export_from_cvat.py --project "Watch Annotations" --output ./exports/
    python export_from_cvat.py --all --output ./exports/
"""

import argparse
import os
import sys
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cvat.scripts.config import CVAT_HOST, CVAT_USERNAME, CVAT_PASSWORD


class CVATExporter:
    """CVAT export client."""
    
    def __init__(self, host: str, username: str, password: str):
        self.host = host.rstrip('/')
        self.session = requests.Session()
        self.username = username
        self.password = password
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with CVAT."""
        login_url = f"{self.host}/api/auth/login"
        response = self.session.post(
            login_url,
            json={"username": self.username, "password": self.password}
        )
        
        if response.status_code != 200:
            raise Exception(f"Authentication failed: {response.text}")
        
        self.session.headers.update({
            'X-CSRFToken': self.session.cookies.get('csrftoken', '')
        })
        
        print(f"Authenticated as {self.username}")
    
    def get_projects(self) -> List[Dict]:
        """Get list of all projects."""
        url = f"{self.host}/api/projects"
        response = self.session.get(url)
        
        if response.status_code != 200:
            return []
        
        return response.json().get("results", [])
    
    def get_project_tasks(self, project_id: int) -> List[Dict]:
        """Get list of tasks in a project."""
        url = f"{self.host}/api/tasks"
        response = self.session.get(url, params={"project_id": project_id})
        
        if response.status_code != 200:
            return []
        
        return response.json().get("results", [])
    
    def get_all_tasks(self) -> List[Dict]:
        """Get list of all tasks."""
        url = f"{self.host}/api/tasks"
        response = self.session.get(url, params={"page_size": 1000})
        
        if response.status_code != 200:
            return []
        
        return response.json().get("results", [])
    
    def get_task_info(self, task_id: int) -> Optional[Dict]:
        """Get task information."""
        url = f"{self.host}/api/tasks/{task_id}"
        response = self.session.get(url)
        
        if response.status_code != 200:
            return None
        
        return response.json()
    
    def export_task_annotations(
        self,
        task_id: int,
        output_path: Path,
        format_name: str = "CVAT for images 1.1"
    ) -> bool:
        """Export annotations from a task.
        
        Args:
            task_id: Task ID
            output_path: Path to save exported annotations
            format_name: Export format name
            
        Returns:
            True if successful
        """
        # Request export
        url = f"{self.host}/api/tasks/{task_id}/annotations"
        params = {
            "format": format_name,
            "action": "download"
        }
        
        response = self.session.get(url, params=params, stream=True)
        
        if response.status_code == 202:
            # Export is being prepared, need to poll
            return self._wait_and_download_export(task_id, output_path, format_name)
        elif response.status_code == 200:
            # Direct download
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Exported annotations to {output_path}")
            return True
        else:
            print(f"Export failed: {response.status_code} - {response.text}")
            return False
    
    def _wait_and_download_export(
        self,
        task_id: int,
        output_path: Path,
        format_name: str,
        timeout: int = 300
    ) -> bool:
        """Wait for export to complete and download."""
        url = f"{self.host}/api/tasks/{task_id}/annotations"
        params = {"format": format_name, "action": "download"}
        
        start = time.time()
        print(f"Waiting for export to complete...")
        
        while time.time() - start < timeout:
            response = self.session.get(url, params=params, stream=True)
            
            if response.status_code == 200:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"Exported annotations to {output_path}")
                return True
            elif response.status_code != 202:
                print(f"Export failed: {response.status_code}")
                return False
            
            time.sleep(2)
        
        print("Export timed out")
        return False
    
    def export_project(self, project_id: int, output_dir: Path) -> int:
        """Export all tasks in a project.
        
        Args:
            project_id: Project ID
            output_dir: Directory to save exports
            
        Returns:
            Number of successfully exported tasks
        """
        tasks = self.get_project_tasks(project_id)
        
        if not tasks:
            print(f"No tasks found in project {project_id}")
            return 0
        
        print(f"Exporting {len(tasks)} tasks from project...")
        
        success_count = 0
        for task in tasks:
            task_id = task["id"]
            task_name = task["name"]
            output_path = output_dir / f"{task_name}_annotations.xml"
            
            print(f"\nExporting task: {task_name} (ID: {task_id})")
            
            if self.export_task_annotations(task_id, output_path):
                success_count += 1
        
        return success_count


def main():
    parser = argparse.ArgumentParser(
        description="Export annotations from CVAT"
    )
    parser.add_argument(
        "--task",
        type=int,
        help="Task ID to export"
    )
    parser.add_argument(
        "--project",
        type=str,
        help="Project name to export all tasks from"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export all tasks"
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output path (file for single task, directory for project/all)"
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
        "--list-projects",
        action="store_true",
        help="List all projects"
    )
    parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="List all tasks"
    )
    
    args = parser.parse_args()
    
    # Check credentials
    if not args.password:
        print("Error: CVAT password required. Set CVAT_PASSWORD or use --password")
        sys.exit(1)
    
    # Initialize client
    try:
        exporter = CVATExporter(args.host, args.username, args.password)
    except Exception as e:
        print(f"Failed to connect to CVAT: {e}")
        sys.exit(1)
    
    # List projects
    if args.list_projects:
        projects = exporter.get_projects()
        print(f"\nFound {len(projects)} projects:")
        for p in projects:
            print(f"  [{p['id']}] {p['name']}")
        return
    
    # List tasks
    if args.list_tasks:
        tasks = exporter.get_all_tasks()
        print(f"\nFound {len(tasks)} tasks:")
        for t in tasks:
            project_name = t.get('project_id', 'No project')
            print(f"  [{t['id']}] {t['name']} (Project: {project_name})")
        return
    
    output_path = Path(args.output)
    
    # Export single task
    if args.task:
        task_info = exporter.get_task_info(args.task)
        if not task_info:
            print(f"Task {args.task} not found")
            sys.exit(1)
        
        # If output is a directory, add filename
        if output_path.is_dir() or str(output_path).endswith('/'):
            output_path = output_path / f"{task_info['name']}_annotations.xml"
        
        success = exporter.export_task_annotations(args.task, output_path)
        sys.exit(0 if success else 1)
    
    # Export project
    if args.project:
        projects = exporter.get_projects()
        project_id = None
        
        for p in projects:
            if p['name'] == args.project:
                project_id = p['id']
                break
        
        if project_id is None:
            print(f"Project '{args.project}' not found")
            sys.exit(1)
        
        count = exporter.export_project(project_id, output_path)
        print(f"\nExported {count} tasks")
        sys.exit(0 if count > 0 else 1)
    
    # Export all
    if args.all:
        tasks = exporter.get_all_tasks()
        
        if not tasks:
            print("No tasks found")
            sys.exit(1)
        
        print(f"Exporting {len(tasks)} tasks...")
        
        success_count = 0
        for task in tasks:
            task_id = task["id"]
            task_name = task["name"]
            task_output = output_path / f"{task_name}_annotations.xml"
            
            print(f"\nExporting task: {task_name}")
            
            if exporter.export_task_annotations(task_id, task_output):
                success_count += 1
        
        print(f"\nExported {success_count}/{len(tasks)} tasks")
        sys.exit(0 if success_count > 0 else 1)
    
    parser.print_help()


if __name__ == "__main__":
    main()
