#!/usr/bin/env python3
"""Generate Laney-chan profile picture using NanoGPT image models.

Usage:
    python scripts/generate_laney_chan.py

Generates square 512x512 images for Telegram profile pics.
"""

import os
import sys
import base64
import requests
from pathlib import Path
from datetime import datetime


def generate_image(prompt: str, model: str = "flux-dev", size: str = "1024x1024", output_dir: Path = None):
    """Generate image using NanoGPT API.

    Args:
        prompt: Text description of image to generate
        model: Image model to use (flux-dev, hidream, recraft-v3, etc.)
        size: Image dimensions (512x512, 1024x1024, etc.)
        output_dir: Directory to save images (defaults to personal/)
    """
    api_key = os.getenv("NANOGPT_API_KEY")
    if not api_key:
        print("❌ NANOGPT_API_KEY not set!")
        print("Set it in your environment or config.")
        sys.exit(1)

    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "personal"
    output_dir.mkdir(exist_ok=True)

    print(f"🎨 Generating image with {model}...")
    print(f"📝 Prompt: {prompt[:80]}...")

    # Make API request
    response = requests.post(
        "https://nano-gpt.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": 1,
        },
        timeout=120  # Image generation can take a while
    )

    if not response.ok:
        print(f"❌ API error: {response.status_code}")
        print(response.text)
        sys.exit(1)

    # Extract image data
    result = response.json()
    image_data = result["data"][0]["b64_json"]

    # Decode and save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"laney_chan_{model}_{timestamp}.png"
    filepath = output_dir / filename

    with open(filepath, "wb") as f:
        f.write(base64.b64decode(image_data))

    print(f"✅ Saved to: {filepath}")
    return filepath


if __name__ == "__main__":
    # Laney-chan prompt: Gibson's Colin Laney meets kawaii aesthetic
    # Balance gritty cyberpunk with approachable design

    prompt = """Anime character design in chibi-adjacent style: young person with short dark hair and glasses,
focused intelligent expression (not smiling, concentrating). Wearing practical tech outfit in dark grays and blues.
Background: dark with subtle holographic data visualization patterns, network graphs, floating AR interface elements.
Cyberpunk aesthetic but clean, not dirty. Character has "I see patterns you don't" energy.
Style: anime but more serious than typical chibi, Gibson's Bridge Trilogy meets Ghost in the Shell.
Square composition 1:1 aspect ratio for profile picture."""

    # Alternative prompts to try:
    alternative_prompts = [
        # More cyberpunk, less chibi
        """Anime-style character portrait: androgynous person with short dark bob cut and round glasses,
intense focused gaze. Dark tactical jacket with blue accents. AR glasses showing data overlays.
Background: dark blue-black with glowing network visualization, data streams, node graphs in cyan/blue.
Cyberpunk aesthetic, Ghost in the Shell meets The Matrix. Serious expression, pattern-recognition savant vibe.
Square 1:1 composition for profile picture.""",

        # Kawaii but with edge
        """Kawaii anime character with serious personality: person with dark hair in bob cut, round black-frame glasses,
neutral/focused expression (not cheerful). Wearing dark techwear outfit.
Eyes show AR data overlays. Background: dark with soft glowing data visualization patterns in blues and purples.
Cute but competent, approachable but intense. Square profile picture format.""",

        # Data-focused design
        """Anime character surrounded by floating holographic data: dark-haired person with glasses looking intently
at invisible patterns in the air. Dark outfit, minimal colors (black, gray, blue accents).
Background filled with network graphs, data nodes, connection lines (subtle, not overwhelming).
Character's eyes reflect data streams. Cyberpunk meets information visualization. Square composition."""
    ]

    print("🎨 Laney-chan Generator")
    print("=" * 50)
    print("\nAvailable models:")
    print("1. flux-dev (default, good balance)")
    print("2. hidream (dreamlike quality)")
    print("3. recraft-v3 (precise control)")
    print("4. flux-pro (highest quality, may cost more)")
    print()

    model_choice = input("Choose model (1-4) or press Enter for default: ").strip()
    models = {
        "1": "flux-dev",
        "2": "hidream",
        "3": "recraft-v3",
        "4": "flux-pro",
        "": "flux-dev"
    }
    model = models.get(model_choice, "flux-dev")

    print("\nPrompt options:")
    print("1. Default (balanced cyberpunk + kawaii)")
    print("2. More cyberpunk, less chibi")
    print("3. Kawaii but with edge")
    print("4. Data visualization focus")
    print()

    prompt_choice = input("Choose prompt (1-4) or press Enter for default: ").strip()

    if prompt_choice == "2":
        prompt = alternative_prompts[0]
    elif prompt_choice == "3":
        prompt = alternative_prompts[1]
    elif prompt_choice == "4":
        prompt = alternative_prompts[2]

    # Generate!
    filepath = generate_image(prompt, model=model, size="1024x1024")

    print("\n✨ Generation complete!")
    print(f"📁 Check: {filepath}")
    print("\nTip: Try different models and prompts to find the right vibe.")
    print("     Edit this script to add your own custom prompts!")
