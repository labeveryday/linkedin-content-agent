"""Code snippet formatting tool for LinkedIn posts."""

from pathlib import Path
from datetime import datetime
from strands import tool


@tool
def format_code_snippet(
    code: str,
    language: str = "python",
    title: str = None,
    output_dir: str = "output",
) -> dict:
    """
    Format a code snippet for LinkedIn.

    Creates a markdown file with syntax-highlighted code that can be
    screenshotted or used with code image generators.

    Args:
        code: The code to format
        language: Programming language for syntax highlighting
        title: Optional title for the snippet
        output_dir: Directory to save the formatted code

    Returns:
        dict with:
            - success: bool
            - file_path: path to saved markdown file
            - formatted: the formatted code block
            - linkedin_text: text version for pasting into LinkedIn

    Note:
        LinkedIn doesn't support code formatting natively.
        Options for sharing code:
        1. Use the formatted markdown with a screenshot tool
        2. Use carbon.now.sh to create a code image
        3. Use the linkedin_text output (monospace-ish with backticks)
    """
    # Clean up code
    code = code.strip()

    # Create markdown formatted version
    formatted = f"```{language}\n{code}\n```"

    # Create LinkedIn-friendly text version
    # LinkedIn renders backticks but no syntax highlighting
    linkedin_text = f"```\n{code}\n```"

    # Add title if provided
    if title:
        formatted = f"## {title}\n\n{formatted}"
        linkedin_text = f"{title}\n\n{linkedin_text}"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"code_snippet_{timestamp}.md"
    file_path = output_path / filename

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(formatted)

    return {
        "success": True,
        "file_path": str(file_path),
        "formatted": formatted,
        "linkedin_text": linkedin_text,
        "language": language,
        "line_count": len(code.split("\n")),
    }


@tool
def create_code_image_prompt(
    code: str,
    language: str = "python",
    theme: str = "dark",
) -> dict:
    """
    Create a prompt for generating a code image with Gemini.

    Args:
        code: The code to visualize
        language: Programming language
        theme: Color theme ("dark" or "light")

    Returns:
        dict with:
            - success: bool
            - prompt: The image generation prompt
            - code: The original code

    Use the returned prompt with generate_image() to create a code image.
    """
    bg_color = "dark gray/black" if theme == "dark" else "white/light gray"
    text_color = "with syntax highlighting colors" if theme == "dark" else "with dark syntax highlighting"

    prompt = f"""Create a clean code snippet image for social media:

- Background: {bg_color}, subtle gradient
- Code: {language} syntax highlighting {text_color}
- Font: monospace, clear and readable
- Style: modern IDE look, rounded corners
- No window chrome or buttons
- Padding around the code

The code to display:
{code}

Make it look professional and shareable on LinkedIn."""

    return {
        "success": True,
        "prompt": prompt,
        "code": code,
        "theme": theme,
    }
