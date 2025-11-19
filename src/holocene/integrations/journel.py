"""Journel integration for reading project data."""

import re
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime


class JournelProject:
    """Represents a journel project."""

    def __init__(self, data: Dict[str, Any]):
        """Initialize from parsed YAML frontmatter."""
        self.id = data.get("id", "")
        self.name = data.get("name", "")
        self.full_name = data.get("full_name", "")
        self.status = data.get("status", "unknown")
        self.tags = data.get("tags", [])
        self.created = data.get("created", "")
        self.last_active = data.get("last_active", "")
        self.completion = data.get("completion", 0)
        self.priority = data.get("priority", "medium")
        self.project_type = data.get("project_type", "regular")
        self.next_steps = data.get("next_steps", "")
        self.blockers = data.get("blockers", "")
        self.github = data.get("github", "")
        self.claude_project = data.get("claude_project", "")

    def is_active(self) -> bool:
        """Check if project is currently active."""
        return self.status == "in-progress"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "tags": self.tags,
            "completion": self.completion,
            "priority": self.priority,
            "type": self.project_type,
            "next_steps": self.next_steps,
            "blockers": self.blockers,
        }


class JournelReader:
    """Reads journel project data."""

    def __init__(self, journel_path: Optional[Path] = None, ignore_projects: List[str] = None):
        """
        Initialize journel reader.

        Args:
            journel_path: Path to .journel directory (defaults to ~/.journel)
            ignore_projects: List of project IDs to ignore
        """
        if journel_path is None:
            journel_path = Path.home() / ".journel"

        self.journel_path = Path(journel_path)
        self.ignore_projects = set(ignore_projects or [])

    def _parse_project_file(self, file_path: Path) -> Optional[JournelProject]:
        """Parse a project markdown file with YAML frontmatter."""
        try:
            content = file_path.read_text(encoding="utf-8")

            # Extract YAML frontmatter
            match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not match:
                return None

            frontmatter = yaml.safe_load(match.group(1))
            return JournelProject(frontmatter)

        except Exception as e:
            # Silently skip files that can't be parsed
            return None

    def get_active_projects(self) -> List[JournelProject]:
        """Get all active (in-progress) projects."""
        projects_dir = self.journel_path / "projects"

        if not projects_dir.exists():
            return []

        projects = []
        for file_path in projects_dir.glob("*.md"):
            project = self._parse_project_file(file_path)

            if project is None:
                continue

            # Skip ignored projects
            if project.id in self.ignore_projects:
                continue

            # Only include active projects
            if project.is_active():
                projects.append(project)

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        projects.sort(key=lambda p: (priority_order.get(p.priority, 99), -p.completion))

        return projects

    def get_project(self, project_id: str) -> Optional[JournelProject]:
        """Get a specific project by ID."""
        file_path = self.journel_path / "projects" / f"{project_id}.md"

        if not file_path.exists():
            # Try completed
            file_path = self.journel_path / "completed" / f"{project_id}.md"

        if not file_path.exists():
            # Try archived
            file_path = self.journel_path / "archived" / f"{project_id}.md"

        if not file_path.exists():
            return None

        return self._parse_project_file(file_path)

    def summarize_active_projects(self) -> str:
        """Create a summary of active projects for LLM context."""
        projects = self.get_active_projects()

        if not projects:
            return "No active projects in journel."

        lines = [f"Active Projects ({len(projects)}):"]

        for project in projects:
            status_parts = [
                f"{project.completion}% complete",
                project.priority,
            ]

            if project.next_steps:
                status_parts.append(f"Next: {project.next_steps[:50]}...")

            if project.blockers:
                status_parts.append(f"⚠️ Blocked: {project.blockers[:30]}...")

            status = " | ".join(status_parts)
            lines.append(f"  • {project.name} ({status})")

        return "\n".join(lines)

    def get_project_tags(self) -> set:
        """Get all unique tags from active projects."""
        projects = self.get_active_projects()
        all_tags = set()

        for project in projects:
            all_tags.update(project.tags)

        return all_tags
