"""
Carbon Code Image Generation Tool

Generate beautiful code screenshots using Carbon (carbon.now.sh)
with Playwright for browser automation.

Features:
- Multiple syntax themes
- Customizable backgrounds
- Various export sizes
- Window style options

For cloud deployment, see carbon_image_cloud.py which uses AgentCore Browser.
"""

import asyncio
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Literal, Optional

from strands import tool

# Carbon configuration types
Theme = Literal[
    "3024-night", "a11y-dark", "blackboard", "base16-dark", "base16-light",
    "cobalt", "dracula", "duotone-dark", "hopscotch", "lucario", "material",
    "monokai", "night-owl", "nord", "oceanic-next", "one-light", "one-dark",
    "panda-syntax", "paraiso-dark", "seti", "shades-of-purple", "solarized-dark",
    "solarized-light", "synthwave-84", "twilight", "verminal", "vscode",
    "yeti", "zenburn"
]

WindowTheme = Literal["none", "sharp", "bw", "boxy"]
ExportSize = Literal["1x", "2x", "4x"]


def _repo_root() -> Path:
    # src/tools/carbon_image.py -> src/tools -> src -> repo root
    return Path(__file__).resolve().parents[2]


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _guess_language_from_path(path: Path) -> str:
    # Carbon language names are generally long-form (python, javascript, etc.)
    ext = path.suffix.lower().lstrip(".")
    return {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "jsx": "javascript",
        "go": "go",
        "rs": "rust",
        "java": "java",
        "kt": "kotlin",
        "swift": "swift",
        "cpp": "cpp",
        "cc": "cpp",
        "cxx": "cpp",
        "c": "c",
        "h": "cpp",
        "hpp": "cpp",
        "cs": "csharp",
        "rb": "ruby",
        "php": "php",
        "sh": "bash",
        "bash": "bash",
        "zsh": "bash",
        "sql": "sql",
        "json": "json",
        "yaml": "yaml",
        "yml": "yaml",
        "toml": "toml",
        "md": "markdown",
    }.get(ext, "auto")


def _build_carbon_url(
    code: str,
    language: str = "auto",
    theme: str = "seti",
    background_color: str = "rgba(171,184,195,1)",
    window_theme: str = "none",
    padding_vertical: int = 56,
    padding_horizontal: int = 56,
    line_numbers: bool = False,
    font_family: str = "Fira Code",
    font_size: int = 14,
) -> str:
    """Build Carbon URL with configuration parameters."""
    # Carbon expects URL-encoded code, not base64
    params = {
        "code": code,
        "l": language,
        "t": theme,
        "bg": background_color,
        "wt": window_theme,
        "pv": str(padding_vertical) + "px",
        "ph": str(padding_horizontal) + "px",
        "ln": str(line_numbers).lower(),
        "fm": font_family,
        "fs": str(font_size) + "px",
        "lh": "133%",
        "wc": "true",  # auto-adjust width
        "ds": "true",  # drop shadow
        "dsyoff": "20px",
        "dsblur": "68px",
        "wa": "true",  # width adjustment
        "es": "2x",  # export size
    }

    query_string = urllib.parse.urlencode(params)
    return f"https://carbon.now.sh/?{query_string}"


async def _capture_carbon_screenshot(
    url: str,
    output_path: Path,
    wait_time: float = 3.0,
    headless: bool = True,
) -> dict:
    """Capture screenshot of Carbon page using local Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "error": "Missing playwright. Install with: pip install playwright && playwright install chromium"
        }

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless)
            page = await browser.new_page()

            try:
                # Navigate to Carbon with our configuration
                await page.goto(url, wait_until="networkidle")

                # Wait for the code to render
                await asyncio.sleep(wait_time)

                # Find the export container (the code window)
                export_container = await page.query_selector(".export-container")

                if export_container:
                    # Screenshot just the code window
                    await export_container.screenshot(path=str(output_path))
                else:
                    # Fallback: screenshot the main container
                    container = await page.query_selector("#__next")
                    if container:
                        await container.screenshot(path=str(output_path))
                    else:
                        # Last resort: full page
                        await page.screenshot(path=str(output_path))

                return {"success": True, "file_path": str(output_path)}

            finally:
                await page.close()
                await browser.close()

    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def generate_code_image(
    code: str,
    language: str = "auto",
    theme: Theme = "seti",
    background_color: str = "rgba(171,184,195,1)",
    window_theme: WindowTheme = "none",
    padding: int = 56,
    line_numbers: bool = False,
    font_family: str = "Fira Code",
    font_size: int = 14,
    output_dir: str = "output",
) -> dict:
    """
    Generate a beautiful code screenshot using Carbon.

    Uses Playwright to render code with Carbon (carbon.now.sh)
    and capture a high-quality screenshot.

    Args:
        code: The source code to render.
        language: Programming language for syntax highlighting.
            Use "auto" for automatic detection. Common options: python, javascript,
            typescript, go, rust, java, cpp, bash, json, yaml, sql, etc.
        theme: Color theme for syntax highlighting. Popular options:
            - "seti" (default) - Dark blue/green
            - "dracula" - Purple/pink dark theme
            - "monokai" - Classic dark theme
            - "one-dark" - Atom One Dark
            - "nord" - Arctic blue theme
            - "night-owl" - Dark theme optimized for night
            - "synthwave-84" - Retro neon theme
            - "vscode" - VS Code default dark
        background_color: Background color in rgba format (e.g., "rgba(171,184,195,1)").
            Use "rgba(0,0,0,0)" for transparent.
        window_theme: Window chrome style - "none", "sharp", "bw", or "boxy".
        padding: Padding around the code in pixels (default: 56).
        line_numbers: Show line numbers (default: False).
        font_family: Font for code (default: "Fira Code").
        font_size: Font size in pixels (default: 14).
        output_dir: Directory to save the image (default: "output").

    Returns:
        dict with keys:
            - success: bool indicating if generation succeeded
            - file_path: path to saved image (if successful)
            - url: Carbon URL used (for debugging)
            - error: error message (if failed)

    Examples:
        # Basic Python code screenshot
        generate_code_image(
            code='print("Hello, World!")',
            language="python"
        )

        # Styled JavaScript with Dracula theme
        generate_code_image(
            code='const greet = (name) => `Hello, ${name}!`;',
            language="javascript",
            theme="dracula",
            background_color="rgba(40,42,54,1)"
        )

        # Transparent background for overlays
        generate_code_image(
            code='fn main() { println!("Rust!"); }',
            language="rust",
            theme="nord",
            background_color="rgba(0,0,0,0)",
            window_theme="none"
        )
    """
    # Build Carbon URL
    carbon_url = _build_carbon_url(
        code=code,
        language=language,
        theme=theme,
        background_color=background_color,
        window_theme=window_theme,
        padding_vertical=padding,
        padding_horizontal=padding,
        line_numbers=line_numbers,
        font_family=font_family,
        font_size=font_size,
    )

    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"carbon_code_{timestamp}.png"
    file_path = output_path / filename

    # Run async capture
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(
        _capture_carbon_screenshot(
            url=carbon_url,
            output_path=file_path,
        )
    )

    # Add URL to result for debugging
    result["url"] = carbon_url

    if result["success"]:
        result["message"] = f"Code image saved to {file_path}"

    return result


@tool
def list_carbon_themes() -> dict:
    """
    List all available Carbon themes for code screenshots.

    Returns:
        dict with keys:
            - themes: list of available theme names
            - recommended: dict of recommended themes by category
    """
    themes = [
        "3024-night", "a11y-dark", "blackboard", "base16-dark", "base16-light",
        "cobalt", "dracula", "duotone-dark", "hopscotch", "lucario", "material",
        "monokai", "night-owl", "nord", "oceanic-next", "one-light", "one-dark",
        "panda-syntax", "paraiso-dark", "seti", "shades-of-purple", "solarized-dark",
        "solarized-light", "synthwave-84", "twilight", "verminal", "vscode",
        "yeti", "zenburn"
    ]

    recommended = {
        "dark_professional": ["seti", "vscode", "one-dark", "material"],
        "dark_vibrant": ["dracula", "synthwave-84", "shades-of-purple", "night-owl"],
        "light": ["one-light", "solarized-light", "base16-light", "yeti"],
        "retro": ["monokai", "zenburn", "twilight", "cobalt"],
        "minimal": ["nord", "oceanic-next", "panda-syntax"],
    }

    return {
        "themes": themes,
        "recommended": recommended,
        "default": "seti",
    }


@tool
def generate_code_image_from_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    language: str = "auto",
    theme: Theme = "seti",
    background_color: str = "rgba(171,184,195,1)",
    window_theme: WindowTheme = "none",
    padding: int = 56,
    line_numbers: bool = False,
    font_family: str = "Fira Code",
    font_size: int = 14,
    output_dir: str = "output",
    max_lines: int = 250,
    max_bytes: int = 250_000,
) -> dict:
    """
    Generate a Carbon code screenshot by reading code directly from a file.

    This is a convenience wrapper around generate_code_image() that:
    - Safely resolves paths within the repo
    - Optionally selects a line range
    - Limits output size (max_lines/max_bytes) to keep screenshots manageable

    Args:
        file_path: Path to the source file (relative to repo root or absolute).
        start_line: 1-based start line (inclusive). Defaults to start of file.
        end_line: 1-based end line (inclusive). Defaults to end of file.
        language: Language for Carbon highlighting ("auto" to infer from extension).
        theme/background_color/window_theme/padding/line_numbers/font_family/font_size/output_dir:
            Same as generate_code_image().
        max_lines: Max lines of code to include in the image (default: 250).
        max_bytes: Max bytes to read from disk (default: 250KB).

    Returns:
        Same dict as generate_code_image(), plus:
            - source_file: repo-relative path
            - source_lines: "start-end" string for the included snippet
    """
    root = _repo_root()
    requested = Path(file_path).expanduser()

    # Resolve relative paths flexibly:
    # - repo root (recommended)
    # - current working directory (useful in scripts)
    # - examples/ subdir fallback (common when running examples)
    candidates: list[Path]
    if requested.is_absolute():
        candidates = [requested]
    else:
        candidates = [
            root / requested,
            Path.cwd() / requested,
            root / "examples" / requested,
        ]

    full_path: Optional[Path] = None
    for cand in candidates:
        resolved = cand.resolve()
        if resolved.exists():
            full_path = resolved
            break

    if full_path is None:
        return {
            "success": False,
            "error": (
                f"File not found: {file_path}\n"
                "Tried: "
                + ", ".join(str(c) for c in candidates)
                + "\nTip: use a repo-root path like 'examples/code_location/sample.py'."
            ),
        }
    if not full_path.is_file():
        return {"success": False, "error": f"Not a file: {file_path}"}
    if not _is_within_root(full_path, root):
        return {
            "success": False,
            "error": "Path is outside the repository root; this tool only reads files within the project.",
        }

    s = 1 if start_line is None else max(1, int(start_line))
    e_req = None if end_line is None else max(1, int(end_line))
    if e_req is not None and e_req < s:
        return {"success": False, "error": f"end_line ({e_req}) must be >= start_line ({s})."}

    # Stream read up to limits
    collected: list[tuple[int, str]] = []
    total_lines = 0
    approx_bytes = 0
    hit_limit = False

    try:
        with full_path.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                total_lines = i
                if i < s:
                    continue
                if e_req is not None and i > e_req:
                    break

                line = line.rstrip("\n")
                collected.append((i, line))

                approx_bytes += len(line.encode("utf-8", errors="replace")) + 1
                if len(collected) >= max_lines or approx_bytes >= max_bytes:
                    hit_limit = True
                    break
    except Exception as ex:
        return {"success": False, "error": f"Failed reading file: {type(ex).__name__}: {ex}"}

    if total_lines == 0:
        return {"success": False, "error": f"File is empty: {str(full_path.relative_to(root))}"}
    if not collected:
        return {
            "success": False,
            "error": f"No lines collected. Check start_line/end_line for {str(full_path.relative_to(root))}.",
        }

    s_out = collected[0][0]
    e_out = collected[-1][0]
    code = "\n".join(line for _, line in collected)

    lang = language if language != "auto" else _guess_language_from_path(full_path)

    result = generate_code_image(
        code=code,
        language=lang,
        theme=theme,
        background_color=background_color,
        window_theme=window_theme,
        padding=padding,
        line_numbers=line_numbers,
        font_family=font_family,
        font_size=font_size,
        output_dir=output_dir,
    )

    # Add source metadata
    result["source_file"] = str(full_path.relative_to(root))
    result["source_lines"] = f"{s_out}-{e_out}"
    if hit_limit:
        result["note"] = "Input snippet was truncated due to max_lines/max_bytes. Use start_line/end_line to narrow."

    return result
