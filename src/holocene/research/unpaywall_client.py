"""Unpaywall API client for finding Open Access papers."""

import requests
from typing import Optional, Dict
import time


class UnpaywallClient:
    """
    Client for Unpaywall API - finds legal, free versions of papers.

    API Docs: https://unpaywall.org/products/api
    """

    def __init__(self, email: str = "research@holocene.local"):
        """
        Initialize Unpaywall client.

        Args:
            email: Your email (required by Unpaywall for polite usage tracking)
        """
        self.base_url = "https://api.unpaywall.org/v2"
        self.email = email
        self.rate_limit_delay = 0.1  # 100ms between requests (polite API usage)
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting to be polite."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def get_oa_status(self, doi: str) -> Optional[Dict]:
        """
        Get Open Access status and PDF location for a DOI.

        Args:
            doi: Paper DOI (e.g., "10.1371/journal.pone.0000308")

        Returns:
            Dictionary with OA information, or None if not found

        Example response:
        {
            "is_oa": True,
            "oa_status": "gold",  # gold/green/hybrid/bronze/closed
            "best_oa_location": {
                "url_for_pdf": "https://...",
                "url": "https://...",
                "version": "publishedVersion",
                "license": "cc-by"
            },
            "oa_locations": [...],  # All OA versions found
            "title": "Paper title",
            "year": 2023
        }
        """
        self._rate_limit()

        try:
            # Clean DOI (remove any URL prefix)
            doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

            url = f"{self.base_url}/{doi}"
            params = {"email": self.email}

            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"⚠️  Unpaywall API error for {doi}: {e}")
            return None

    def parse_oa_info(self, unpaywall_data: Dict) -> Dict:
        """
        Parse Unpaywall response into simplified OA information.

        Args:
            unpaywall_data: Raw Unpaywall API response

        Returns:
            Simplified dict with OA info
        """
        is_oa = unpaywall_data.get("is_oa", False)
        oa_status = unpaywall_data.get("oa_status", "closed")

        pdf_url = None
        oa_color = None

        if is_oa:
            best_location = unpaywall_data.get("best_oa_location")
            if best_location:
                pdf_url = best_location.get("url_for_pdf") or best_location.get("url")

                # Determine OA "color"
                # Gold = Published in OA journal
                # Green = Author archived version (repository)
                # Hybrid = Paid OA in subscription journal
                # Bronze = Free to read but no clear license
                oa_color = {
                    "gold": "🟡",
                    "green": "🟢",
                    "hybrid": "🟠",
                    "bronze": "🟤",
                    "closed": "🔴"
                }.get(oa_status, "⚪")

        return {
            "is_open_access": is_oa,
            "oa_status": oa_status,
            "oa_color": oa_color,
            "pdf_url": pdf_url,
            "title": unpaywall_data.get("title"),
            "year": unpaywall_data.get("year")
        }

    def check_bulk(self, dois: list[str]) -> Dict[str, Dict]:
        """
        Check OA status for multiple DOIs (with rate limiting).

        Args:
            dois: List of DOIs to check

        Returns:
            Dictionary mapping DOI -> OA info
        """
        results = {}

        for i, doi in enumerate(dois, 1):
            print(f"Checking OA status ({i}/{len(dois)}): {doi}")

            data = self.get_oa_status(doi)
            if data:
                results[doi] = self.parse_oa_info(data)
            else:
                results[doi] = {
                    "is_open_access": False,
                    "oa_status": "not_found",
                    "oa_color": None,
                    "pdf_url": None
                }

        return results
