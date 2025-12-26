"""Tool for writing LinkedIn posts with learned patterns."""

import json
from pathlib import Path
from datetime import datetime
from strands import tool


@tool
def write_post(
    content: str,
    title: str = None,
    save: bool = True,
    output_dir: str = "output",
) -> dict:
    """
    Save a generated LinkedIn post to a file.

    Args:
        content: The generated post content
        title: Optional title for the file (used in filename)
        save: Whether to save to file (default: True)
        output_dir: Directory to save the post (default: "output")

    Returns:
        dict with:
            - success: bool
            - file_path: path to saved file (if saved)
            - content: the post content
            - word_count: number of words
    """
    word_count = len(content.split())

    if not save:
        return {
            "success": True,
            "content": content,
            "word_count": word_count,
            "saved": False,
        }

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = title.lower().replace(" ", "_")[:30] if title else "post"
    filename = f"{slug}_{timestamp}.md"
    file_path = output_path / filename

    # Save with metadata
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"---\n")
        f.write(f"generated: {datetime.now().isoformat()}\n")
        if title:
            f.write(f"title: {title}\n")
        f.write(f"word_count: {word_count}\n")
        f.write(f"---\n\n")
        f.write(content)

    return {
        "success": True,
        "file_path": str(file_path),
        "content": content,
        "word_count": word_count,
        "saved": True,
    }


@tool
def load_patterns(storage_path: str = "patterns/patterns.json") -> dict:
    """
    Load previously saved patterns from JSON storage.

    Call this FIRST when creating posts to use learned patterns.

    Args:
        storage_path: Path to patterns file (default: patterns/patterns.json)

    Returns:
        dict with:
            - success: bool
            - patterns: the saved patterns (hooks, structure, tone, ctas, topics)
            - message: status message
    """
    path = Path(storage_path)

    if not path.exists():
        return {
            "success": False,
            "patterns": None,
            "message": f"No patterns found at {path}. Run 'learn' first to analyze creator posts.",
        }

    with open(path, "r") as f:
        data = json.load(f)

    patterns = data.get("patterns", {})

    if not patterns:
        return {
            "success": False,
            "patterns": None,
            "message": "Patterns file exists but is empty. Run 'learn' to extract patterns.",
        }

    return {
        "success": True,
        "patterns": patterns,
        "updated_at": data.get("updated_at"),
        "message": f"Loaded patterns from {path}",
    }


@tool
def save_patterns(patterns: dict, storage_path: str = "patterns/patterns.json") -> dict:
    """
    Save extracted patterns to JSON storage.

    Args:
        patterns: The patterns dict to save (hooks, structure, tone, ctas, topics)
        storage_path: Path to save patterns (default: patterns/patterns.json)

    Returns:
        dict with success status and file path
    """
    path = Path(storage_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing patterns if present
    existing = {}
    if path.exists():
        with open(path, "r") as f:
            existing = json.load(f)

    # Merge patterns
    existing["updated_at"] = datetime.now().isoformat()
    if "patterns" not in existing:
        existing["patterns"] = {}

    existing["patterns"].update(patterns)

    with open(path, "w") as f:
        json.dump(existing, f, indent=2)

    return {
        "success": True,
        "file_path": str(path),
        "message": f"Patterns saved to {path}",
    }
