"""
Gemini Video Generation Tool

Supports Veo 3.1, Veo 3, and Veo 2 for high-quality video generation.
Features:
- Text-to-video generation
- Image-to-video generation (animate from first frame)
- Frame interpolation (first and last frame)
- Reference images (up to 3 for Veo 3.1)
- Video extension (extend previously generated videos)
- Aspect ratio and resolution control
- Native audio generation (Veo 3.1/3)
"""

import os
import time
from pathlib import Path
from datetime import datetime
from typing import Literal, Optional, List

from strands import tool
from google import genai
from google.genai import types


VideoModel = Literal[
    "veo-3.1-generate-preview",
    "veo-3.1-fast-generate-preview",
    "veo-3.0-generate-001",
    "veo-3.0-fast-generate-001",
    "veo-2.0-generate-001",
]
AspectRatio = Literal["16:9", "9:16"]
Resolution = Literal["720p", "1080p"]
Duration = Literal[4, 5, 6, 8]


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


def _load_image(image_path: str) -> types.Image:
    """Load an image file and return an Image object."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with open(path, "rb") as f:
        image_bytes = f.read()

    mime_type = _get_mime_type(path)
    return types.Image(image_bytes=image_bytes, mime_type=mime_type)


def _save_video(client, generated_video, output_dir: str, prefix: str, api_key: str) -> dict:
    """Save generated video to file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.mp4"
    file_path = output_path / filename

    # Try to download using client.files.download first
    video_obj = generated_video.video if hasattr(generated_video, 'video') else None

    if video_obj:
        try:
            # Use the SDK's download method
            client.files.download(file=video_obj)
            video_obj.save(str(file_path))
            return {"success": True, "file_path": str(file_path)}
        except Exception:
            pass

        # Fallback: try video_bytes
        if hasattr(video_obj, 'video_bytes') and video_obj.video_bytes:
            with open(file_path, "wb") as f:
                f.write(video_obj.video_bytes)
            return {"success": True, "file_path": str(file_path)}

        # Fallback: try URI download
        if hasattr(video_obj, 'uri') and video_obj.uri:
            import requests
            # Handle both query param formats
            separator = "&" if "?" in video_obj.uri else "?"
            url = f"{video_obj.uri}{separator}key={api_key}"
            response = requests.get(url, allow_redirects=True)
            if response.status_code == 200:
                with open(file_path, "wb") as f:
                    f.write(response.content)
                return {"success": True, "file_path": str(file_path)}
            return {"success": False, "error": f"Failed to download video: HTTP {response.status_code}"}

    return {"success": False, "error": "No video data in response"}


def _poll_operation(client, operation, max_wait_seconds: int) -> dict:
    """Poll operation until complete or timeout."""
    start_time = time.time()
    while not operation.done:
        if time.time() - start_time > max_wait_seconds:
            return {"success": False, "error": f"Video generation timed out after {max_wait_seconds} seconds"}
        time.sleep(10)
        operation = client.operations.get(operation)

    if operation.error:
        return {"success": False, "error": f"Generation failed: {operation.error}"}

    if not operation.response or not operation.response.generated_videos:
        return {"success": False, "error": "No video generated"}

    return {"success": True, "operation": operation}


@tool
def generate_video(
    prompt: str,
    model: VideoModel = "veo-3.1-generate-preview",
    duration_seconds: Duration = 8,
    aspect_ratio: Optional[AspectRatio] = None,
    resolution: Optional[Resolution] = None,
    negative_prompt: Optional[str] = None,
    reference_images: Optional[List[str]] = None,
    output_dir: str = "output",
    max_wait_seconds: int = 600,
) -> dict:
    """
    Generate a video using Veo models (text-to-video).

    Args:
        prompt: Text description of the video to generate. Be specific about motion,
                camera angles, lighting, style, and audio cues (dialogue, sound effects).
        model: Veo model to use. Options:
               - "veo-3.1-generate-preview" (default, best quality, audio, 720p/1080p)
               - "veo-3.1-fast-generate-preview" (faster, audio)
               - "veo-3.0-generate-001" (stable, audio)
               - "veo-3.0-fast-generate-001" (fast, audio)
               - "veo-2.0-generate-001" (silent, no audio)
        duration_seconds: Video duration. Options: 4, 5, 6, 8 (default: 8).
                         Note: 5 is only valid for Veo 2. 1080p requires 8s duration.
        aspect_ratio: Video aspect ratio. Options: "16:9" (default), "9:16".
        resolution: Video resolution. Options: "720p" (default), "1080p" (8s only for Veo 3.1).
        negative_prompt: Text describing what NOT to include in the video.
        reference_images: List of paths to reference images (up to 3, Veo 3.1 only).
                         Used to guide content/style while preserving subject appearance.
        output_dir: Directory to save the generated video (default: "output").
        max_wait_seconds: Maximum time to wait for generation (default: 600).

    Returns:
        dict with keys:
            - success: bool indicating if generation succeeded
            - file_path: path to saved video (if successful)
            - message: status message
            - model: model used
            - error: error message (if failed)

    Examples:
        # Basic text-to-video with audio
        generate_video(prompt="A cinematic shot of a majestic lion in the savannah")

        # With dialogue and sound effects (Veo 3.1 generates audio natively)
        generate_video(
            prompt="Close up of two people. A man murmurs, 'This must be it.' The woman whispers, 'What did you find?'",
            model="veo-3.1-generate-preview"
        )

        # Portrait video for social media
        generate_video(prompt="A dancer performing ballet", aspect_ratio="9:16")

        # High resolution 1080p (requires 8s duration)
        generate_video(prompt="Aerial drone shot of mountains", resolution="1080p", duration_seconds=8)

        # With reference images for consistent subjects
        generate_video(
            prompt="A woman in a flamingo dress walks through a lagoon",
            reference_images=["dress.png", "woman.png", "glasses.png"]
        )
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    # Validate model-specific constraints
    is_veo31 = model.startswith("veo-3.1")
    is_veo3 = model.startswith("veo-3")
    is_veo2 = model.startswith("veo-2")

    # Duration validation
    if is_veo2:
        valid_durations = [5, 6, 8]
    else:
        valid_durations = [4, 6, 8]

    if duration_seconds not in valid_durations:
        return {"success": False, "error": f"Invalid duration for {model}. Must be one of: {valid_durations}"}

    # Resolution validation
    if resolution == "1080p":
        if is_veo2:
            return {"success": False, "error": "1080p resolution not supported for Veo 2"}
        if duration_seconds != 8:
            return {"success": False, "error": "1080p resolution requires duration_seconds=8"}

    # Reference images only for Veo 3.1
    if reference_images:
        if not is_veo31:
            return {"success": False, "error": "Reference images only supported with Veo 3.1 models"}
        if len(reference_images) > 3:
            return {"success": False, "error": "Maximum 3 reference images supported"}

    try:
        client = genai.Client(api_key=api_key)

        # Build config
        config_kwargs = {}
        if duration_seconds:
            config_kwargs["duration_seconds"] = duration_seconds
        if aspect_ratio:
            config_kwargs["aspect_ratio"] = aspect_ratio
        if resolution:
            config_kwargs["resolution"] = resolution
        if negative_prompt:
            config_kwargs["negative_prompt"] = negative_prompt

        # Add reference images if provided
        if reference_images:
            refs = []
            for img_path in reference_images:
                try:
                    img = _load_image(img_path)
                    refs.append(types.VideoGenerationReferenceImage(
                        image=img,
                        reference_type="asset"
                    ))
                except FileNotFoundError as e:
                    return {"success": False, "error": str(e)}
            config_kwargs["reference_images"] = refs

        config = types.GenerateVideosConfig(**config_kwargs) if config_kwargs else None

        # Start generation
        operation = client.models.generate_videos(
            model=model,
            prompt=prompt,
            config=config,
        )

        # Poll for completion
        result = _poll_operation(client, operation, max_wait_seconds)
        if not result["success"]:
            return result

        # Save video
        generated_video = result["operation"].response.generated_videos[0]
        save_result = _save_video(client, generated_video, output_dir, "gemini_video", api_key)

        if not save_result["success"]:
            return save_result

        return {
            "success": True,
            "file_path": save_result["file_path"],
            "message": f"Video saved to {save_result['file_path']}",
            "model": model,
            "duration": duration_seconds,
            "has_audio": not is_veo2,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def generate_video_from_image(
    prompt: str,
    image_path: str,
    model: VideoModel = "veo-3.1-generate-preview",
    duration_seconds: Duration = 8,
    aspect_ratio: Optional[AspectRatio] = None,
    resolution: Optional[Resolution] = None,
    negative_prompt: Optional[str] = None,
    last_frame_path: Optional[str] = None,
    output_dir: str = "output",
    max_wait_seconds: int = 600,
) -> dict:
    """
    Generate a video from an image using Veo models (image-to-video).

    The input image becomes the first frame of the video. Optionally specify
    a last frame for interpolation (Veo 3.1 only).

    Args:
        prompt: Text description of the video motion and animation.
        image_path: Path to the input image (first frame).
        model: Veo model to use (see generate_video for options).
        duration_seconds: Video duration. Options: 4, 5, 6, 8 (default: 8).
        aspect_ratio: Video aspect ratio. Options: "16:9", "9:16".
        resolution: Video resolution. Options: "720p", "1080p".
        negative_prompt: Text describing what NOT to include.
        last_frame_path: Path to the last frame image for interpolation (Veo 3.1 only).
                        Creates a smooth transition between first and last frames.
        output_dir: Directory to save the generated video (default: "output").
        max_wait_seconds: Maximum time to wait for generation (default: 600).

    Returns:
        dict with keys:
            - success: bool indicating if generation succeeded
            - file_path: path to saved video (if successful)
            - message: status message
            - error: error message (if failed)

    Examples:
        # Animate a still image
        generate_video_from_image(
            prompt="The kitten wakes up and stretches",
            image_path="sleeping_kitten.png"
        )

        # Frame interpolation (first to last frame transition)
        generate_video_from_image(
            prompt="A ghostly woman on a swing slowly fades away",
            image_path="woman_on_swing.png",
            last_frame_path="empty_swing.png"
        )
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    is_veo31 = model.startswith("veo-3.1")
    is_veo2 = model.startswith("veo-2")

    # Last frame only for Veo 3.1
    if last_frame_path and not is_veo31:
        return {"success": False, "error": "Frame interpolation (last_frame) only supported with Veo 3.1 models"}

    # Duration validation
    if is_veo2:
        valid_durations = [5, 6, 8]
    else:
        valid_durations = [4, 6, 8]

    if duration_seconds not in valid_durations:
        return {"success": False, "error": f"Invalid duration for {model}. Must be one of: {valid_durations}"}

    # Resolution validation
    if resolution == "1080p":
        if is_veo2:
            return {"success": False, "error": "1080p resolution not supported for Veo 2"}
        if duration_seconds != 8:
            return {"success": False, "error": "1080p resolution requires duration_seconds=8"}

    try:
        # Load first frame image
        first_image = _load_image(image_path)
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}

    try:
        client = genai.Client(api_key=api_key)

        # Build config
        config_kwargs = {}
        if duration_seconds:
            config_kwargs["duration_seconds"] = duration_seconds
        if aspect_ratio:
            config_kwargs["aspect_ratio"] = aspect_ratio
        if resolution:
            config_kwargs["resolution"] = resolution
        if negative_prompt:
            config_kwargs["negative_prompt"] = negative_prompt

        # Add last frame for interpolation
        if last_frame_path:
            try:
                last_image = _load_image(last_frame_path)
                config_kwargs["last_frame"] = last_image
            except FileNotFoundError as e:
                return {"success": False, "error": str(e)}

        config = types.GenerateVideosConfig(**config_kwargs) if config_kwargs else None

        # Start generation with image
        operation = client.models.generate_videos(
            model=model,
            prompt=prompt,
            image=first_image,
            config=config,
        )

        # Poll for completion
        result = _poll_operation(client, operation, max_wait_seconds)
        if not result["success"]:
            return result

        # Save video
        generated_video = result["operation"].response.generated_videos[0]
        prefix = "gemini_video_interpolation" if last_frame_path else "gemini_video_i2v"
        save_result = _save_video(client, generated_video, output_dir, prefix, api_key)

        if not save_result["success"]:
            return save_result

        return {
            "success": True,
            "file_path": save_result["file_path"],
            "message": f"Video saved to {save_result['file_path']}",
            "model": model,
            "source_image": image_path,
            "last_frame": last_frame_path,
            "duration": duration_seconds,
            "has_audio": not is_veo2,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def extend_video(
    prompt: str,
    video_path: str,
    model: Literal["veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"] = "veo-3.1-generate-preview",
    output_dir: str = "output",
    max_wait_seconds: int = 600,
) -> dict:
    """
    Extend a previously generated Veo video by 7 seconds (Veo 3.1 only).

    Takes a Veo-generated video and continues the action with a new prompt.
    Can extend videos up to 20 times (max 148 seconds total).

    Args:
        prompt: Text description of what should happen in the extended portion.
        video_path: Path to the Veo-generated video to extend.
                   Must be 720p, 16:9 or 9:16, and under 141 seconds.
        model: Veo 3.1 model to use. Options:
               - "veo-3.1-generate-preview" (default)
               - "veo-3.1-fast-generate-preview"
        output_dir: Directory to save the extended video (default: "output").
        max_wait_seconds: Maximum time to wait for generation (default: 600).

    Returns:
        dict with keys:
            - success: bool indicating if extension succeeded
            - file_path: path to saved video (if successful)
            - message: status message
            - error: error message (if failed)

    Notes:
        - Only works with Veo-generated videos (not arbitrary videos)
        - Input video must be 720p resolution
        - Output combines original + extended video
        - Voice cannot be effectively extended if not in last 1 second

    Examples:
        # Extend a butterfly video
        extend_video(
            prompt="The butterfly lands on an orange flower. A puppy runs up.",
            video_path="butterfly.mp4"
        )
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"success": False, "error": "GOOGLE_API_KEY environment variable not set"}

    video_file = Path(video_path)
    if not video_file.exists():
        return {"success": False, "error": f"Video file not found: {video_path}"}

    try:
        client = genai.Client(api_key=api_key)

        # Read video file
        with open(video_file, "rb") as f:
            video_bytes = f.read()

        # Create video object
        video = types.Video(video_bytes=video_bytes, mime_type="video/mp4")

        # Config for extension (must be 720p, 8s extension)
        config = types.GenerateVideosConfig(
            number_of_videos=1,
            resolution="720p",
        )

        # Start extension
        operation = client.models.generate_videos(
            model=model,
            prompt=prompt,
            video=video,
            config=config,
        )

        # Poll for completion
        result = _poll_operation(client, operation, max_wait_seconds)
        if not result["success"]:
            return result

        # Save video
        generated_video = result["operation"].response.generated_videos[0]
        save_result = _save_video(client, generated_video, output_dir, "gemini_video_extended", api_key)

        if not save_result["success"]:
            return save_result

        return {
            "success": True,
            "file_path": save_result["file_path"],
            "message": f"Extended video saved to {save_result['file_path']}",
            "model": model,
            "source_video": video_path,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
