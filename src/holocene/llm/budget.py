"""Budget tracking for LLM API calls."""

import json
import requests
from pathlib import Path
from datetime import datetime, date
from typing import Optional


class BudgetTracker:
    """Tracks daily LLM API usage against budget using NanoGPT API."""

    def __init__(
        self,
        data_dir: Path,
        daily_limit: int = 2000,
        api_key: Optional[str] = None,
        base_url: str = "https://nano-gpt.com/api/v1"
    ):
        """
        Initialize budget tracker.

        Args:
            data_dir: Directory to store budget data (fallback)
            daily_limit: Maximum API calls per day
            api_key: NanoGPT API key
            base_url: NanoGPT API base URL
        """
        self.data_dir = Path(data_dir)
        self.daily_limit = daily_limit
        self.usage_file = self.data_dir / "llm_usage.json"
        self.api_key = api_key
        self.base_url = base_url

        # Ensure data dir exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load_usage(self) -> dict:
        """Load usage data from file."""
        if not self.usage_file.exists():
            return {}

        with open(self.usage_file, "r") as f:
            return json.load(f)

    def _save_usage(self, usage: dict):
        """Save usage data to file."""
        with open(self.usage_file, "w") as f:
            json.dump(usage, f, indent=2)

    def _fetch_usage_from_api(self) -> Optional[dict]:
        """
        Fetch subscription usage from NanoGPT API.

        Returns:
            Usage data dict or None if fetch fails
        """
        if not self.api_key:
            return None

        try:
            # NanoGPT subscription usage endpoint
            url = "https://nano-gpt.com/api/subscription/v1/usage"
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            # Silently fall back to local tracking
            return None

    def get_today_usage(self) -> int:
        """
        Get today's API call count.

        Tries to fetch from NanoGPT API first, falls back to local tracking.
        """
        # Try API first
        api_usage = self._fetch_usage_from_api()
        if api_usage and "daily" in api_usage:
            return api_usage["daily"].get("used", 0)

        # Fall back to local tracking
        usage = self._load_usage()
        today = date.today().isoformat()
        return usage.get(today, 0)

    def get_usage_details(self) -> Optional[dict]:
        """
        Get detailed usage information from NanoGPT API.

        Returns:
            Full usage dict with daily and monthly stats, or None if unavailable
        """
        return self._fetch_usage_from_api()

    def increment_usage(self, count: int = 1):
        """Increment today's usage count."""
        usage = self._load_usage()
        today = date.today().isoformat()
        usage[today] = usage.get(today, 0) + count
        self._save_usage(usage)

    def check_budget(self) -> bool:
        """Check if we're within budget for today."""
        return self.get_today_usage() < self.daily_limit

    def remaining_budget(self) -> int:
        """Get remaining budget for today."""
        return max(0, self.daily_limit - self.get_today_usage())

    def reset_old_entries(self, keep_days: int = 30):
        """Remove usage entries older than keep_days."""
        usage = self._load_usage()
        today = date.today()

        # Filter to recent dates
        filtered = {}
        for date_str, count in usage.items():
            entry_date = date.fromisoformat(date_str)
            days_ago = (today - entry_date).days
            if days_ago <= keep_days:
                filtered[date_str] = count

        self._save_usage(filtered)
