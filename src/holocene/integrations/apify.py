"""Apify integration for web scraping."""

from apify_client import ApifyClient as OfficialApifyClient
from typing import List, Dict


class ApifyClient:
    """Wrapper around official Apify client."""

    def __init__(self, api_token: str):
        """
        Initialize Apify client.

        Args:
            api_token: Apify API token
        """
        self.client = OfficialApifyClient(api_token)

    def run_actor_and_get_results(
        self,
        actor_id: str,
        run_input: Dict,
        timeout: int = 600
    ) -> List[Dict]:
        """
        Run actor and return results in one call.

        Args:
            actor_id: Actor ID (e.g., "karamelo/mercadolivre-scraper-brasil-portugues")
            run_input: Input configuration
            timeout: Maximum wait time in seconds

        Returns:
            List of scraped items
        """
        # Run the actor and wait for completion
        run_info = self.client.actor(actor_id).call(
            run_input=run_input,
            timeout_secs=timeout
        )

        # Get the dataset with results
        dataset_id = run_info.get("defaultDatasetId")
        if not dataset_id:
            raise RuntimeError("No dataset ID in actor run result")

        # Fetch all items from the dataset
        items = list(self.client.dataset(dataset_id).iterate_items())

        return items
