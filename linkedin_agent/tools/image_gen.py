"""Image generation tools using Gemini."""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Literal

from strands import tool
from google import genai
from google.genai import types


# Type definitions
AspectRatio = Literal["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
Resolution = Literal["1K", "2K", "4K"]

# Default footer CTA for LinkedIn images
DEFAULT_FOOTER = "linkedin.com/in/duanlightfoot"

# Default model
IMAGE_MODEL = "gemini-3-pro-image-preview"


def _get_mime_type(path: Path) -> str:
    """Get MIME type from file extension."""
    suffix = path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    return mime_map.get(suffix, "image/png")


def _load_image_part(image_path: str) -> types.Part:
    """Load an image file and return a Part object."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with open(path, "rb") as f:
        image_bytes = f.read()

    mime_type = _get_mime_type(path)
    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)


def _build_generate_config(
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
) -> types.GenerateContentConfig:
    """Build the generation config with optional image settings."""
    config_kwargs = {
        "response_modalities": ["IMAGE", "TEXT"],
    }

    # Build image config if any options provided
    # Uses ImageConfig with aspectRatio and imageSize (e.g., "1024x1024")
    image_config_kwargs = {}
    if aspect_ratio:
        image_config_kwargs["aspectRatio"] = aspect_ratio
    if resolution:
        # Map resolution to imageSize
        size_map = {
            "1K": "1024x1024",
            "2K": "2048x2048",
            "4K": "4096x4096",
        }
        image_config_kwargs["imageSize"] = size_map.get(resolution, resolution)

    if image_config_kwargs:
        config_kwargs["imageConfig"] = types.ImageConfig(**image_config_kwargs)

    return types.GenerateContentConfig(**config_kwargs)


def _generate_and_save(
    client: genai.Client,
    contents: list,
    output_dir: str,
    filename_prefix: str,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
) -> dict:
    """Common generation and save logic."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    config = _build_generate_config(aspect_ratio, resolution)

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=config,
    )

    image_data = None
    text_response = None

    if response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "thought") and part.thought:
                continue
            if hasattr(part, "inline_data") and part.inline_data:
                image_data = part.inline_data.data
            elif hasattr(part, "text") and part.text:
                text_response = part.text

    if not image_data:
        return {
            "success": False,
            "error": "No image generated",
            "text_response": text_response,
        }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.png"
    file_path = output_path / filename

    with open(file_path, "wb") as f:
        f.write(image_data)

    return {
        "success": True,
        "file_path": str(file_path),
        "message": f"Image saved to {file_path}",
    }


# =============================================================================
# INFOGRAPHIC - Brand-styled (black/pink minimalist)
# =============================================================================

@tool
def generate_infographic(
    key_points: List[str],
    title: str = "Key Points",
    topic: Optional[str] = None,
    footer: Optional[str] = DEFAULT_FOOTER,
    aspect_ratio: Optional[AspectRatio] = "1:1",
    resolution: Optional[Resolution] = None,
    additional_instructions: Optional[str] = None,
    output_dir: str = "output",
) -> dict:
    """
    Generate a brand-styled infographic (black/pink minimalist).

    BRAND STYLE IS AUTOMATIC. Just provide content - styling is built-in.

    Args:
        key_points: REQUIRED - List of exact points to display.
        title: Headline/title for the image.
        topic: Subject matter context (e.g., "AI Agents").
        footer: CTA text at bottom (default: LinkedIn profile). None to disable.
        aspect_ratio: "1:1", "16:9", "9:16", "4:3", etc. (default: "1:1")
        resolution: "1K", "2K", "4K" (default: auto)
        additional_instructions: Layout tweaks only, NOT styling.
        output_dir: Save directory (default: "output")

    Example:
        generate_infographic(
            key_points=["Point 1", "Point 2", "Point 3"],
            title="3 Key Insights",
            aspect_ratio="1:1"
        )
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    if not key_points or len(key_points) == 0:
        return {"success": False, "error": "key_points is required"}

    try:
        client = genai.Client(api_key=api_key)
        contents = []

        # Build brand-styled prompt
        points_text = "\n".join([f"{i+1}. {point}" for i, point in enumerate(key_points)])

        prompt = f"""Create a minimalist technical infographic on PURE BLACK background (#000000).

TITLE: {title}

EXACT POINTS TO DISPLAY (use these exact words):
{points_text}

DESIGN REQUIREMENTS:
- PURE BLACK background (#000000) - no gradients, solid black only
- White text for main content
- Pink/magenta (#FF1493 or similar) for accents, highlights, and numbering
- Simple white line icons/drawings for each point
- Clean, minimalist technical documentation style
- Flat design - NO gradients anywhere
- Title at top in bold white or pink
- Each numbered point with simple icon and exact text
- Good spacing between elements
"""
        if footer:
            prompt += f"""
FOOTER:
- Thin pink/magenta line separator near bottom
- Small LinkedIn icon (white) followed by "{footer}" in white text
- Footer should be subtle but readable
"""
        if topic:
            prompt += f"- Theme/topic context: {topic}\n"
        if additional_instructions:
            prompt += f"- Additional: {additional_instructions}\n"

        contents.append(prompt)

        return _generate_and_save(
            client, contents, output_dir, "infographic",
            aspect_ratio=aspect_ratio, resolution=resolution
        )

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }


# =============================================================================
# MEME - Creative/fun images
# =============================================================================

@tool
def generate_meme(
    prompt: str,
    reference_image: Optional[str] = None,
    aspect_ratio: Optional[AspectRatio] = "1:1",
    resolution: Optional[Resolution] = None,
    output_dir: str = "output",
) -> dict:
    """
    Generate a meme or fun creative image.

    Use for memes, jokes, creative visuals. Can use a reference image.

    Args:
        prompt: Description of the meme. Include visual concept, text, style.
        reference_image: Optional image path to base the meme on.
        aspect_ratio: "1:1", "16:9", "9:16", etc. (default: "1:1")
        resolution: "1K", "2K", "4K" (default: auto)
        output_dir: Save directory (default: "output")

    Examples:
        generate_meme(prompt="Developer shocked face, text 'It was the semicolon'")

        generate_meme(
            prompt="Turn this into a 'this is fine' meme",
            reference_image="photo.jpg"
        )
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    try:
        client = genai.Client(api_key=api_key)
        contents = []

        if reference_image:
            try:
                contents.append(_load_image_part(reference_image))
                contents.append(f"Using this image as reference/inspiration: {prompt}")
            except FileNotFoundError as e:
                return {"success": False, "error": str(e)}
        else:
            contents.append(prompt)

        return _generate_and_save(
            client, contents, output_dir, "meme",
            aspect_ratio=aspect_ratio, resolution=resolution
        )

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }


# =============================================================================
# CUSTOM IMAGE - Free-form prompt
# =============================================================================

@tool
def generate_custom_image(
    prompt: str,
    reference_image: Optional[str] = None,
    aspect_ratio: Optional[AspectRatio] = "1:1",
    resolution: Optional[Resolution] = None,
    output_dir: str = "output",
) -> dict:
    """
    Generate a custom image from a free-form prompt.

    Full control over style - no automatic brand styling.

    Args:
        prompt: Complete description including subject, style, colors, layout.
        reference_image: Optional reference image for guidance.
        aspect_ratio: "1:1", "16:9", "9:16", etc. (default: "1:1")
        resolution: "1K", "2K", "4K" (default: auto)
        output_dir: Save directory (default: "output")

    Examples:
        generate_custom_image(
            prompt="AWS architecture diagram, white background, blue icons"
        )

        generate_custom_image(
            prompt="Cyberpunk version with neon colors",
            reference_image="photo.jpg",
            aspect_ratio="16:9"
        )
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    try:
        client = genai.Client(api_key=api_key)
        contents = []

        if reference_image:
            try:
                contents.append(_load_image_part(reference_image))
                contents.append(f"Using this image as reference: {prompt}")
            except FileNotFoundError as e:
                return {"success": False, "error": str(e)}
        else:
            contents.append(prompt)

        return _generate_and_save(
            client, contents, output_dir, "custom_image",
            aspect_ratio=aspect_ratio, resolution=resolution
        )

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }


# =============================================================================
# EDIT IMAGE - Modify existing images
# =============================================================================

@tool
def edit_image(
    image_path: str,
    prompt: str,
    aspect_ratio: Optional[AspectRatio] = None,
    resolution: Optional[Resolution] = None,
    output_dir: str = "output",
) -> dict:
    """
    Edit an existing image using multi-turn conversation.

    Use for: changing text, modifying elements, style adjustments.
    Recommended for iterative refinement of generated images.

    Args:
        image_path: Path to the image to edit.
        prompt: Description of edits to make. Be specific.
        aspect_ratio: Output aspect ratio (optional, keeps original if not set).
        resolution: "1K", "2K", "4K" (default: auto)
        output_dir: Save directory (default: "output")

    Examples:
        edit_image(
            image_path="output/infographic_xxx.png",
            prompt="Change the title to 'Updated Title'"
        )

        edit_image(
            image_path="output/meme_xxx.png",
            prompt="Make the text bigger and add a watermark"
        )
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    try:
        client = genai.Client(api_key=api_key)
        contents = []

        try:
            contents.append(_load_image_part(image_path))
        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}

        contents.append(f"Edit this image: {prompt}")

        return _generate_and_save(
            client, contents, output_dir, "edited",
            aspect_ratio=aspect_ratio, resolution=resolution
        )

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }
