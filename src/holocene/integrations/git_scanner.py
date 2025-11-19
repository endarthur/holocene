"""Local git repository scanner and activity tracker."""

import re
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict


class GitRepo:
    """Represents a local git repository."""

    def __init__(self, path: Path):
        """Initialize from repository path."""
        self.path = Path(path)
        self.name = self.path.name
        self._remote_url = None
        self._is_fork = None
        self._owner = None

    def _run_git(self, *args) -> Optional[str]:
        """Run a git command in the repo directory."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.path)] + list(args),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    @property
    def remote_url(self) -> Optional[str]:
        """Get the remote origin URL."""
        if self._remote_url is None:
            output = self._run_git("config", "--get", "remote.origin.url")
            self._remote_url = output if output else ""
        return self._remote_url if self._remote_url else None

    @property
    def is_github(self) -> bool:
        """Check if this is a GitHub repository."""
        url = self.remote_url
        return url and ("github.com" in url) if url else False

    @property
    def github_slug(self) -> Optional[str]:
        """Extract owner/repo from GitHub URL."""
        url = self.remote_url
        if not url or "github.com" not in url:
            return None

        # Handle both HTTPS and SSH URLs
        # https://github.com/owner/repo.git
        # git@github.com:owner/repo.git
        match = re.search(r'github\.com[:/]([^/]+/[^/]+?)(\.git)?$', url)
        if match:
            return match.group(1)
        return None

    def get_commits_since(self, since: datetime) -> List[Dict[str, Any]]:
        """Get commits since a specific date."""
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")

        # Git log with format: hash|author|date|subject
        log = self._run_git(
            "log",
            f"--since={since_str}",
            "--all",
            "--format=%H|%an|%ai|%s"
        )

        if not log:
            return []

        commits = []
        for line in log.split("\n"):
            if not line.strip():
                continue

            parts = line.split("|", 3)
            if len(parts) == 4:
                commit_hash, author, date_str, subject = parts
                commits.append({
                    "hash": commit_hash[:7],
                    "author": author,
                    "date": date_str,
                    "subject": subject,
                })

        return commits

    def get_commit_count_since(self, since: datetime) -> int:
        """Get count of commits since a specific date."""
        return len(self.get_commits_since(since))

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "path": str(self.path),
            "remote_url": self.remote_url,
            "github_slug": self.github_slug,
            "is_github": self.is_github,
        }


class GitScanner:
    """Scans local directories for git repositories."""

    def __init__(self, scan_path: Path, github_token: Optional[str] = None):
        """
        Initialize git scanner.

        Args:
            scan_path: Directory to scan for repos
            github_token: Optional GitHub API token for enriching public repos
        """
        self.scan_path = Path(scan_path)
        self.github_token = github_token
        self._repos_cache = None

    def scan_repos(self) -> List[GitRepo]:
        """Scan for all git repositories in scan_path."""
        if self._repos_cache is not None:
            return self._repos_cache

        repos = []

        if not self.scan_path.exists():
            return repos

        # Look for .git directories (one level deep)
        for item in self.scan_path.iterdir():
            if not item.is_dir():
                continue

            git_dir = item / ".git"
            if git_dir.exists():
                repos.append(GitRepo(item))

        self._repos_cache = repos
        return repos

    def get_repo_by_name(self, name: str) -> Optional[GitRepo]:
        """Get a repo by name."""
        repos = self.scan_repos()
        for repo in repos:
            if repo.name.lower() == name.lower():
                return repo
        return None

    def get_activity_since(self, since: datetime) -> Dict[str, Any]:
        """Get activity summary across all repos."""
        repos = self.scan_repos()

        total_commits = 0
        active_repos = []
        commits_by_repo = {}

        for repo in repos:
            commit_count = repo.get_commit_count_since(since)
            if commit_count > 0:
                total_commits += commit_count
                active_repos.append(repo.name)
                commits_by_repo[repo.name] = commit_count

        return {
            "total_commits": total_commits,
            "active_repos": active_repos,
            "commits_by_repo": commits_by_repo,
            "total_repos_scanned": len(repos),
        }

    def summarize_activity(self, since: datetime) -> str:
        """Create a text summary of git activity."""
        activity = self.get_activity_since(since)

        if activity["total_commits"] == 0:
            return f"No git commits found in {len(activity['total_repos_scanned'])} scanned repos."

        lines = [
            f"Git Activity ({activity['total_commits']} commits across {len(activity['active_repos'])} repos):"
        ]

        # Sort by commit count
        sorted_repos = sorted(
            activity["commits_by_repo"].items(),
            key=lambda x: x[1],
            reverse=True
        )

        for repo_name, count in sorted_repos:
            lines.append(f"  • {repo_name}: {count} commit{'s' if count != 1 else ''}")

        return "\n".join(lines)

    def match_with_journel_projects(self, journel_projects) -> Dict[str, Optional[GitRepo]]:
        """Match journel projects with local git repos."""
        repos = self.scan_repos()
        matches = {}

        for project in journel_projects:
            # Try exact name match first
            repo = self.get_repo_by_name(project.name)

            if not repo and hasattr(project, 'github') and project.github:
                # Try to extract repo name from GitHub URL
                match = re.search(r'github\.com[:/][^/]+/([^/]+?)(\.git)?$', project.github)
                if match:
                    repo_name = match.group(1)
                    repo = self.get_repo_by_name(repo_name)

            matches[project.id] = repo

        return matches
