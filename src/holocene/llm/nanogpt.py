"""NanoGPT API client."""

import requests
from typing import Optional, List, Dict, Any


class NanoGPTClient:
    """Client for NanoGPT API (OpenAI-compatible)."""

    def __init__(self, api_key: str, base_url: str = "https://nano-gpt.com/api/v1"):
        """
        Initialize NanoGPT client.

        Args:
            api_key: NanoGPT API key
            base_url: Base URL for API
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-ai/DeepSeek-V3.1",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """
        Call chat completion API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model ID to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds (default: 60, use 300+ for large batches)

        Returns:
            API response dict
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        response = self.session.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()

        return response.json()

    def get_response_text(self, response: Dict[str, Any]) -> str:
        """Extract response text from API response."""
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Invalid response format: {e}")

    def simple_prompt(
        self,
        prompt: str,
        model: str = "deepseek-ai/DeepSeek-V3.1",
        system: Optional[str] = None,
        temperature: float = 0.7,
        timeout: int = 60,
    ) -> str:
        """
        Simple single-turn prompt.

        Args:
            prompt: User prompt
            model: Model ID
            system: Optional system message
            temperature: Sampling temperature
            timeout: Request timeout in seconds (default: 60, use 300+ for large batches)

        Returns:
            Response text
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        response = self.chat_completion(messages, model=model, temperature=temperature, timeout=timeout)
        return self.get_response_text(response)
