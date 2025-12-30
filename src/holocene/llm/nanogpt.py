"""NanoGPT API client with tool/function calling support."""

import json
import requests
from typing import Optional, List, Dict, Any, Callable


class NanoGPTClient:
    """Client for NanoGPT API (OpenAI-compatible) with tool support."""

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
        messages: List[Dict[str, Any]],
        model: str = "deepseek-ai/DeepSeek-V3.1",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call chat completion API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model ID to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds (default: 60, use 300+ for large batches)
            tools: List of tool definitions (OpenAI format)
            tool_choice: "auto", "none", or {"type": "function", "function": {"name": "..."}}

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

        if tools:
            payload["tools"] = tools

        if tool_choice:
            payload["tool_choice"] = tool_choice

        response = self.session.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()

        return response.json()

    def has_tool_calls(self, response: Dict[str, Any]) -> bool:
        """Check if response contains tool calls."""
        try:
            message = response["choices"][0]["message"]
            return "tool_calls" in message and message["tool_calls"]
        except (KeyError, IndexError):
            return False

    def get_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tool calls from response.

        Returns:
            List of tool call dicts with 'id', 'function.name', 'function.arguments'
        """
        try:
            return response["choices"][0]["message"].get("tool_calls", [])
        except (KeyError, IndexError):
            return []

    def run_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, Callable],
        model: str = "deepseek-ai/DeepSeek-V3.1",
        temperature: float = 0.7,
        max_iterations: int = 10,
        timeout: int = 60,
        on_tool_call: Optional[Callable[[str, int], None]] = None,
    ) -> str:
        """
        Run a conversation with tool calling support.

        Handles the agent loop: LLM → tool calls → execute → LLM → ... → final response.

        Args:
            messages: Initial messages (system + user)
            tools: Tool definitions in OpenAI format
            tool_handlers: Dict mapping tool names to handler functions
            model: Model ID to use
            temperature: Sampling temperature
            max_iterations: Maximum tool call iterations (safety limit)
            timeout: Request timeout per API call
            on_tool_call: Optional callback(tool_name, iteration) for progress updates

        Returns:
            Final response text after all tool calls are resolved
        """
        import logging
        import time
        logger = logging.getLogger(__name__)

        conversation = list(messages)  # Copy to avoid mutating original
        start_time = time.time()

        for iteration in range(max_iterations):
            # Call LLM
            iter_start = time.time()
            logger.info(f"[NanoGPT] Iteration {iteration+1}/{max_iterations}, calling API...")
            response = self.chat_completion(
                messages=conversation,
                model=model,
                temperature=temperature,
                tools=tools,
                tool_choice="auto",
                timeout=timeout,
            )
            logger.info(f"[NanoGPT] API responded in {time.time()-iter_start:.1f}s")

            # Check if we have tool calls
            if not self.has_tool_calls(response):
                # No tool calls = final response
                return self.get_response_text(response)

            # Process tool calls
            assistant_message = response["choices"][0]["message"]
            conversation.append(assistant_message)

            tool_calls = self.get_tool_calls(response)

            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_id = tool_call["id"]

                # Notify callback if provided
                if on_tool_call:
                    try:
                        on_tool_call(tool_name, iteration + 1)
                    except Exception:
                        pass  # Don't let callback errors break the loop

                # Parse arguments
                try:
                    args = json.loads(tool_call["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                # Execute tool
                if tool_name in tool_handlers:
                    try:
                        tool_start = time.time()
                        logger.info(f"[NanoGPT] Executing tool: {tool_name}")
                        result = tool_handlers[tool_name](**args)
                        logger.info(f"[NanoGPT] Tool {tool_name} completed in {time.time()-tool_start:.1f}s")
                        result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                    except Exception as e:
                        logger.error(f"[NanoGPT] Tool {tool_name} failed: {e}")
                        result_str = json.dumps({"error": str(e)})
                else:
                    result_str = json.dumps({"error": f"Unknown tool: {tool_name}"})

                # Add tool result to conversation
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result_str,
                })

        # Max iterations reached
        return "I've reached the maximum number of tool calls. Please try a simpler query."

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

    def get_subscription_usage(self) -> Dict[str, Any]:
        """Get subscription usage information.

        Returns:
            Dict with usage data (prompts used, limit, etc.)
        """
        try:
            # NanoGPT uses a different base URL for subscription endpoints
            response = self.session.get(
                "https://nano-gpt.com/api/subscription/v1/usage",
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
