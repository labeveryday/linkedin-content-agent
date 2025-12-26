#!/usr/bin/env python3
"""LinkedIn Content Agent CLI."""

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

app = typer.Typer(
    name="linkedin-agent",
    help="Learn from creators, generate authentic LinkedIn posts.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def learn(
    source: str = typer.Option(
        "creators",
        "--source", "-s",
        help="Directory containing posts to analyze",
    ),
):
    """Analyze posts and learn patterns from successful creators."""
    from linkedin_agent.agent import create_agent

    source_path = Path(source)
    if not source_path.exists():
        console.print(f"[red]Error:[/red] Directory not found: {source}")
        raise typer.Exit(1)

    text_files = list(source_path.glob("*.md")) + list(source_path.glob("*.txt"))
    # Match extensions in post_analyzer.py (case-insensitive via both cases)
    image_files = (
        list(source_path.glob("*.png")) + list(source_path.glob("*.PNG")) +
        list(source_path.glob("*.jpg")) + list(source_path.glob("*.JPG")) +
        list(source_path.glob("*.jpeg")) + list(source_path.glob("*.JPEG")) +
        list(source_path.glob("*.webp")) + list(source_path.glob("*.WEBP")) +
        list(source_path.glob("*.heic")) + list(source_path.glob("*.HEIC"))
    )
    # Deduplicate in case filesystem is case-insensitive
    image_files = list({f.resolve(): f for f in image_files}.values())

    if not text_files and not image_files:
        console.print(f"[red]Error:[/red] No posts found in {source}")
        console.print("Add .md/.txt files or .png/.jpg screenshots")
        raise typer.Exit(1)

    parts = []
    if text_files:
        parts.append(f"{len(text_files)} text posts")
    if image_files:
        parts.append(f"{len(image_files)} screenshots")

    console.print(f"\n[bold]Learning from {' and '.join(parts)} in {source}/[/bold]\n")

    agent, _ = create_agent(mode="learn")

    prompt = f"""Analyze all posts in the '{source}' directory.

1. Use analyze_posts to read text posts and list image files
2. If there are screenshots/images, use understand_image with image_paths to analyze them all at once
3. Extract patterns (hooks, structure, tone, CTAs, topics, visual patterns)
4. Use save_patterns to store what you learned
5. Summarize the key patterns you found"""

    with console.status("[bold green]Analyzing posts..."):
        result = agent(prompt)

    console.print(Panel(str(result), title="Analysis Complete"))


@app.command()
def create(
    topic: str = typer.Argument(..., help="Topic or prompt for the post"),
    image: bool = typer.Option(False, "--image", "-i", help="Generate an image"),
    video: bool = typer.Option(False, "--video", help="Generate a video (4-8s with audio)"),
    code: bool = typer.Option(False, "--code", "-c", help="Include code snippet"),
    variations: int = typer.Option(1, "--variations", "-v", help="Number of variations"),
):
    """Generate a LinkedIn post based on learned patterns."""
    from linkedin_agent.agent import create_agent
    from linkedin_agent.storage import PatternStore

    # Check if patterns exist
    store = PatternStore()
    patterns = store.load()

    if not patterns.get("patterns"):
        console.print("[yellow]Warning:[/yellow] No patterns learned yet.")
        console.print("Run [bold]linkedin-agent learn[/bold] first to analyze posts.\n")

    agent, _ = create_agent(mode="create")

    prompt = f"Write a LinkedIn post about: {topic}"

    if variations > 1:
        prompt += f"\n\nGenerate {variations} different variations."

    if image:
        prompt += "\n\nAlso generate an engaging image to accompany the post."

    if video:
        prompt += "\n\nAlso generate a short video (4-8 seconds) to accompany the post. Use aspect_ratio='9:16' for vertical mobile-optimized format. The video should capture attention in the LinkedIn feed."

    if code:
        prompt += "\n\nInclude a relevant code snippet, formatted for sharing."

    prompt += "\n\nSave the post(s) using write_post."

    console.print(f"\n[bold]Generating post about:[/bold] {topic}\n")

    media_types = []
    if image:
        media_types.append("image")
    if video:
        media_types.append("video")
    if code:
        media_types.append("code")

    status_msg = "Creating content"
    if media_types:
        status_msg += f" with {', '.join(media_types)}"
    status_msg += "..."

    with console.status(f"[bold green]{status_msg}"):
        result = agent(prompt)

    console.print(Panel(str(result), title="Generated Content"))


@app.command()
def patterns():
    """View learned patterns."""
    from linkedin_agent.storage import PatternStore
    import json

    store = PatternStore()
    data = store.load()

    if not data.get("patterns"):
        console.print("[yellow]No patterns learned yet.[/yellow]")
        console.print("Run [bold]linkedin-agent learn[/bold] to analyze posts.")
        return

    # Summary
    summary = store.get_summary()
    if summary:
        console.print(Panel(summary, title="Pattern Summary"))

    # Full patterns
    console.print("\n[bold]Full Patterns:[/bold]")
    console.print_json(json.dumps(data["patterns"], indent=2))


@app.command()
def chat():
    """Start interactive chat mode."""
    from linkedin_agent.agent import run_interactive

    run_interactive()


@app.command()
def init():
    """Initialize project folders and example files."""
    folders = ["creators", "output", "patterns"]

    for folder in folders:
        Path(folder).mkdir(exist_ok=True)
        console.print(f"[green]Created:[/green] {folder}/")

    # Create example post
    example_path = Path("creators/example.md")
    if not example_path.exists():
        example_content = """# Example LinkedIn Post

Here's a pattern I see with successful LinkedIn posts:

They start with a hook that grabs attention.

Then they deliver value in short, punchy paragraphs.

They use:
- Bullet points for lists
- Short sentences
- White space

And they end with a question to drive engagement.

What patterns have you noticed in viral posts?

---
(Replace this with real posts from creators you admire)
"""
        example_path.write_text(example_content)
        console.print(f"[green]Created:[/green] {example_path}")

    console.print("\n[bold]Project initialized![/bold]")
    console.print("\nNext steps:")
    console.print("1. Add posts to the [bold]creators/[/bold] folder")
    console.print("2. Run [bold]linkedin-agent learn[/bold] to analyze them")
    console.print("3. Run [bold]linkedin-agent create 'your topic'[/bold] to generate posts")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
