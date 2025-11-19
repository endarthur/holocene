#!/usr/bin/env python3
"""Test NanoGPT vision model capabilities."""

import sys
import os
import base64
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from holocene.config import load_config
from holocene.llm import NanoGPTClient


def encode_image(image_path: Path) -> str:
    """Encode image to base64."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def test_vision(image_path: Path, model: str = "qwen25-vl-72b-instruct"):
    """Test vision model with an image."""

    config = load_config()

    if not config.llm.api_key:
        print("Error: NANOGPT_API_KEY not set")
        return 1

    print(f"Testing vision model: {model}")
    print(f"Image: {image_path}")
    print()

    # Encode image
    print("Encoding image...")
    base64_image = encode_image(image_path)

    # Create client
    client = NanoGPTClient(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url
    )

    # Prepare messages with image
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Please describe what you see in this image in detail."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
        }
    ]

    print("Calling vision model...")
    try:
        response = client.chat_completion(
            messages=messages,
            model=model,
            temperature=0.7
        )

        result = client.get_response_text(response)

        print("\n" + "="*60)
        print("VISION MODEL RESPONSE:")
        print("="*60)
        print(result)
        print("="*60)

        return 0

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test NanoGPT vision capabilities")
    parser.add_argument("image", type=Path, help="Path to image file")
    parser.add_argument(
        "--model",
        default="qwen25-vl-72b-instruct",
        help="Vision model to use (default: qwen25-vl-72b-instruct)"
    )

    args = parser.parse_args()

    if not args.image.exists():
        print(f"Error: Image not found: {args.image}")
        sys.exit(1)

    sys.exit(test_vision(args.image, args.model))
