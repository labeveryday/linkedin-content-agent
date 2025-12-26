"""Tool for analyzing LinkedIn posts and extracting patterns."""

from pathlib import Path
from strands import tool


@tool
def analyze_posts(posts_directory: str = "creators") -> dict:
    """
    Read and prepare LinkedIn posts for pattern analysis.

    This tool reads all markdown/text files AND lists image files from the
    specified directory. Text content is returned directly. For images,
    use the understand_image tool to analyze each one.

    Args:
        posts_directory: Directory containing post files (default: "creators")

    Returns:
        dict with:
            - success: bool
            - posts: list of {filename, content} dicts (text files)
            - images: list of image file paths (for use with understand_image)
            - count: total number of files found
            - error: error message if failed
    """
    posts_path = Path(posts_directory)

    if not posts_path.exists():
        return {
            "success": False,
            "error": f"Directory not found: {posts_directory}",
            "posts": [],
            "images": [],
            "count": 0,
        }

    posts = []
    images = []
    text_extensions = {".md", ".txt", ".markdown"}
    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".heic"}

    for file_path in posts_path.iterdir():
        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()

        if suffix in text_extensions:
            try:
                content = file_path.read_text(encoding="utf-8")
                posts.append({
                    "filename": file_path.name,
                    "content": content,
                    "length": len(content.split()),
                    "type": "text",
                })
            except Exception as e:
                posts.append({
                    "filename": file_path.name,
                    "error": str(e),
                    "type": "text",
                })

        elif suffix in image_extensions:
            images.append({
                "filename": file_path.name,
                "path": str(file_path.absolute()),
                "type": "image",
            })

    total = len(posts) + len(images)

    if total == 0:
        return {
            "success": False,
            "error": f"No post files found in {posts_directory}. Add .md, .txt, .png, or .jpg files.",
            "posts": [],
            "images": [],
            "count": 0,
        }

    message_parts = []
    if posts:
        message_parts.append(f"{len(posts)} text posts")
    if images:
        message_parts.append(f"{len(images)} screenshots/images")

    return {
        "success": True,
        "posts": posts,
        "images": images,
        "count": total,
        "message": f"Found {' and '.join(message_parts)} to analyze. Use understand_image to analyze screenshots.",
    }
