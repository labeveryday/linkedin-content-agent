"""
Gemini Image Understanding Tool

Uses Gemini models for image analysis, object detection, and segmentation.
Features:
- Image captioning and visual Q&A
- Object detection with bounding boxes (Gemini 2.0+)
- Segmentation with contour masks (Gemini 2.5+)
"""

import os
import json
import base64
import io
from pathlib import Path
from datetime import datetime
from typing import Literal, Optional, List

from strands import tool
from google import genai
from google.genai import types

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


ImageModel = Literal[
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
]

MediaResolution = Literal[
    "media_resolution_low",
    "media_resolution_medium",
    "media_resolution_high",
]


def _get_mime_type(path: Path) -> str:
    """Get MIME type from file extension."""
    suffix = path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }
    return mime_map.get(suffix, "image/jpeg")


def _load_image_part(image_path: str) -> types.Part:
    """Load an image file and return a Part object."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with open(path, "rb") as f:
        image_bytes = f.read()

    mime_type = _get_mime_type(path)
    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)


def _parse_json_response(text: str) -> list:
    """Parse JSON from model response, handling markdown fencing."""
    # Remove markdown fencing if present
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "```json":
            text = "\n".join(lines[i + 1:])
            text = text.split("```")[0]
            break
        elif line.strip() == "```":
            text = "\n".join(lines[i + 1:])
            text = text.split("```")[0]
            break

    return json.loads(text.strip())


@tool
def understand_image(
    prompt: str,
    image_path: Optional[str] = None,
    image_url: Optional[str] = None,
    image_paths: Optional[List[str]] = None,
    model: ImageModel = "gemini-2.5-flash",
    media_resolution: Optional[MediaResolution] = None,
) -> dict:
    """
    Analyze images using Gemini models for captioning, visual Q&A, and more.

    Args:
        prompt: Question or instruction about the image(s).
                Examples: "Caption this image", "What objects are in this image?",
                "Compare these two images", "Is there a cat in this photo?"
        image_path: Path to a single image file.
        image_url: URL of an image to analyze.
        image_paths: List of paths for multiple images (up to 3600).
        model: Gemini model to use. Options:
               - "gemini-2.5-flash" (default, fast)
               - "gemini-2.5-pro" (higher quality)
               - "gemini-3-flash-preview" (latest fast)
               - "gemini-3-pro-preview" (latest quality)
        media_resolution: Control vision processing detail (Gemini 3 only).
                         Options: "media_resolution_low", "media_resolution_medium",
                         "media_resolution_high". Higher = better detail but more tokens.

    Returns:
        dict with keys:
            - success: bool indicating if analysis succeeded
            - response: text response from the model
            - model: model used
            - error: error message (if failed)

    Examples:
        # Caption an image
        understand_image(prompt="Caption this image", image_path="photo.jpg")

        # Visual Q&A
        understand_image(prompt="What color is the car?", image_path="car.png")

        # Compare multiple images
        understand_image(
            prompt="What is different between these images?",
            image_paths=["before.jpg", "after.jpg"]
        )

        # Analyze image from URL
        understand_image(prompt="Describe this image", image_url="https://example.com/image.jpg")
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    # Validate inputs
    sources = [image_path, image_url, image_paths]
    provided = sum(1 for s in sources if s)
    if provided == 0:
        return {"success": False, "error": "Provide image_path, image_url, or image_paths"}
    if provided > 1:
        return {"success": False, "error": "Provide only one of: image_path, image_url, or image_paths"}

    try:
        client = genai.Client(api_key=api_key)

        # Build contents
        contents = []

        if image_path:
            contents.append(_load_image_part(image_path))
        elif image_url:
            import requests
            response = requests.get(image_url)
            if response.status_code != 200:
                return {"success": False, "error": f"Failed to fetch image: HTTP {response.status_code}"}
            # Detect mime type from content-type header or URL
            content_type = response.headers.get("content-type", "image/jpeg")
            if not content_type.startswith("image/"):
                content_type = "image/jpeg"
            contents.append(types.Part.from_bytes(data=response.content, mime_type=content_type))
        elif image_paths:
            for img_path in image_paths:
                contents.append(_load_image_part(img_path))

        # Add prompt after images
        contents.append(prompt)

        # Build config
        config_kwargs = {}
        if media_resolution and model.startswith("gemini-3"):
            config_kwargs["media_resolution"] = media_resolution

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        return {
            "success": True,
            "response": response.text,
            "model": model,
        }

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def detect_objects(
    image_path: str,
    prompt: Optional[str] = None,
    model: ImageModel = "gemini-2.5-flash",
    output_dir: Optional[str] = None,
) -> dict:
    """
    Detect objects in an image and get bounding box coordinates (Gemini 2.0+).

    Args:
        image_path: Path to the image file.
        prompt: Custom detection prompt. Default detects all prominent items.
                Examples: "Detect all faces", "Find all green objects",
                "Label items with their allergens"
        model: Gemini model to use (2.0+ required for detection).
        output_dir: Optional directory to save annotated image with boxes.

    Returns:
        dict with keys:
            - success: bool indicating if detection succeeded
            - objects: list of detected objects with labels and bounding boxes
            - image_size: (width, height) of the image
            - annotated_image: path to annotated image (if output_dir provided)
            - error: error message (if failed)

    Notes:
        - Bounding boxes are in format [x1, y1, x2, y2] (absolute pixels)
        - Raw coordinates from model are [ymin, xmin, ymax, xmax] normalized to 0-1000
        - Requires PIL (Pillow) for annotated image output

    Examples:
        # Detect all objects
        detect_objects(image_path="photo.jpg")

        # Custom detection
        detect_objects(image_path="photo.jpg", prompt="Detect all faces")

        # Save annotated image
        detect_objects(image_path="photo.jpg", output_dir="output")
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    if not HAS_PIL:
        return {"success": False, "error": "PIL (Pillow) is required for object detection. Install with: pip install Pillow"}

    path = Path(image_path)
    if not path.exists():
        return {"success": False, "error": f"Image file not found: {image_path}"}

    try:
        client = genai.Client(api_key=api_key)

        # Load image to get dimensions
        image = Image.open(path)
        width, height = image.size

        # Build prompt
        if prompt:
            detection_prompt = f"{prompt}. Return JSON with box_2d as [ymin, xmin, ymax, xmax] normalized to 0-1000 and label for each object."
        else:
            detection_prompt = "Detect all prominent items in the image. The box_2d should be [ymin, xmin, ymax, xmax] normalized to 0-1000."

        # Request JSON response
        config = types.GenerateContentConfig(
            response_mime_type="application/json"
        )

        response = client.models.generate_content(
            model=model,
            contents=[_load_image_part(image_path), detection_prompt],
            config=config,
        )

        # Parse response
        bounding_boxes = json.loads(response.text)

        # Convert normalized coordinates to absolute pixels
        objects = []
        for item in bounding_boxes:
            if "box_2d" not in item:
                continue

            box = item["box_2d"]
            # Model returns [ymin, xmin, ymax, xmax] normalized to 0-1000
            abs_y1 = int(box[0] / 1000 * height)
            abs_x1 = int(box[1] / 1000 * width)
            abs_y2 = int(box[2] / 1000 * height)
            abs_x2 = int(box[3] / 1000 * width)

            objects.append({
                "label": item.get("label", "object"),
                "box": [abs_x1, abs_y1, abs_x2, abs_y2],  # [x1, y1, x2, y2]
                "box_normalized": box,  # Original [ymin, xmin, ymax, xmax] 0-1000
            })

        result = {
            "success": True,
            "objects": objects,
            "image_size": {"width": width, "height": height},
            "model": model,
        }

        # Optionally draw bounding boxes and save
        if output_dir and objects:
            from PIL import ImageDraw, ImageFont

            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Create annotated image
            annotated = image.copy()
            draw = ImageDraw.Draw(annotated)

            # Colors for different objects
            colors = ["red", "blue", "green", "orange", "purple", "cyan", "magenta", "yellow"]

            for i, obj in enumerate(objects):
                color = colors[i % len(colors)]
                box = obj["box"]
                draw.rectangle(box, outline=color, width=3)
                draw.text((box[0], box[1] - 15), obj["label"], fill=color)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            annotated_path = output_path / f"detected_{timestamp}.png"
            annotated.save(annotated_path)
            result["annotated_image"] = str(annotated_path)

        return result

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse detection response: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def segment_objects(
    image_path: str,
    prompt: str,
    model: ImageModel = "gemini-2.5-flash",
    output_dir: str = "output",
    threshold: int = 127,
) -> dict:
    """
    Segment objects in an image and get contour masks (Gemini 2.5+).

    Args:
        image_path: Path to the image file.
        prompt: Description of what to segment.
                Examples: "wooden and glass items", "all people", "the red car"
        model: Gemini model to use (2.5+ required for segmentation).
        output_dir: Directory to save mask overlays (default: "output").
        threshold: Mask binarization threshold 0-255 (default: 127).

    Returns:
        dict with keys:
            - success: bool indicating if segmentation succeeded
            - segments: list of segments with labels, boxes, and mask paths
            - image_size: (width, height) of the image
            - error: error message (if failed)

    Notes:
        - Requires PIL (Pillow) and numpy for mask processing
        - Saves individual mask overlays to output_dir
        - Masks are probability maps (0-255) binarized at threshold

    Examples:
        # Segment wooden and glass items
        segment_objects(image_path="table.jpg", prompt="wooden and glass items")

        # Segment people
        segment_objects(image_path="crowd.jpg", prompt="all people")
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    if not HAS_PIL:
        return {"success": False, "error": "PIL (Pillow) is required. Install with: pip install Pillow"}

    if not HAS_NUMPY:
        return {"success": False, "error": "numpy is required. Install with: pip install numpy"}

    path = Path(image_path)
    if not path.exists():
        return {"success": False, "error": f"Image file not found: {image_path}"}

    try:
        client = genai.Client(api_key=api_key)

        # Load and optionally resize image
        image = Image.open(path)
        original_size = image.size

        # Resize if too large (recommended max 1024)
        max_dim = 1024
        if max(image.size) > max_dim:
            image.thumbnail([max_dim, max_dim], Image.Resampling.LANCZOS)

        width, height = image.size

        # Build segmentation prompt
        segmentation_prompt = f"""
Give the segmentation masks for {prompt}.
Output a JSON list of segmentation masks where each entry contains the 2D
bounding box in the key "box_2d", the segmentation mask in key "mask", and
the text label in the key "label". Use descriptive labels.
"""

        # Disable thinking for better segmentation results
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )

        # Save resized image temporarily for upload
        temp_path = Path(output_dir) / "_temp_resized.png"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        image.save(temp_path)

        response = client.models.generate_content(
            model=model,
            contents=[_load_image_part(str(temp_path)), segmentation_prompt],
            config=config,
        )

        # Clean up temp file
        temp_path.unlink(missing_ok=True)

        # Parse response
        items = _parse_json_response(response.text)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        segments = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for i, item in enumerate(items):
            if "box_2d" not in item or "mask" not in item:
                continue

            # Get bounding box
            box = item["box_2d"]
            y0 = int(box[0] / 1000 * height)
            x0 = int(box[1] / 1000 * width)
            y1 = int(box[2] / 1000 * height)
            x1 = int(box[3] / 1000 * width)

            # Skip invalid boxes
            if y0 >= y1 or x0 >= x1:
                continue

            # Process mask
            mask_str = item["mask"]
            if not mask_str.startswith("data:image/png;base64,"):
                continue

            # Decode mask
            mask_str = mask_str.removeprefix("data:image/png;base64,")
            mask_data = base64.b64decode(mask_str)
            mask = Image.open(io.BytesIO(mask_data))

            # Resize mask to match bounding box
            mask = mask.resize((x1 - x0, y1 - y0), Image.Resampling.BILINEAR)
            mask_array = np.array(mask)

            # Create overlay
            overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))

            # Apply mask with color
            colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]
            color = colors[i % len(colors)]

            for y in range(y0, y1):
                for x in range(x0, x1):
                    my, mx = y - y0, x - x0
                    if my < mask_array.shape[0] and mx < mask_array.shape[1]:
                        if mask_array[my, mx] > threshold:
                            overlay.putpixel((x, y), (*color, 150))

            # Save overlay
            label = item.get("label", f"segment_{i}")
            safe_label = "".join(c if c.isalnum() else "_" for c in label)
            overlay_filename = f"{safe_label}_{timestamp}_{i}_overlay.png"
            mask_filename = f"{safe_label}_{timestamp}_{i}_mask.png"

            # Save mask
            mask.save(output_path / mask_filename)

            # Create and save composite
            composite = Image.alpha_composite(image.convert('RGBA'), overlay)
            composite.save(output_path / overlay_filename)

            segments.append({
                "label": label,
                "box": [x0, y0, x1, y1],
                "mask_path": str(output_path / mask_filename),
                "overlay_path": str(output_path / overlay_filename),
            })

        return {
            "success": True,
            "segments": segments,
            "image_size": {"width": width, "height": height, "original": original_size},
            "model": model,
        }

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse segmentation response: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
