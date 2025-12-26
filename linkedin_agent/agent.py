"""LinkedIn Content Agent - Main agent definition."""

from dotenv import load_dotenv

# Load environment variables FIRST (before hub imports)
load_dotenv()

from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands_tools import http_request, editor

from .models import anthropic_model
from .tools import (
    analyze_posts,
    write_post,
    load_patterns,
    generate_infographic,
    generate_meme,
    generate_custom_image,
    edit_image,
    format_code_snippet,
    understand_image,
    detect_objects,
    generate_video,
    generate_video_from_image,
    extend_video,
    generate_code_image,
    generate_code_image_from_file,
    list_carbon_themes,
)
from .tools.post_writer import save_patterns
from .hooks import LoggingHook
from .hub import (
    create_session_manager,
    MetricsExporter,
    S3PromptManager,
    AgentRegistry,
)
from .hub.session import generate_run_id


# =============================================================================
# CONFIGURATION
# =============================================================================

AGENT_ID = "linkedin-content-agent"
AGENT_NAME = "LinkedIn Content Agent"
PROMPT_VERSION = "v1"


# System prompts for different modes
LEARN_PROMPT = """You are a LinkedIn content analyst. Your job is to analyze posts from successful creators and extract patterns that make their content effective.

You can analyze BOTH text files AND screenshots/images of posts.

**For text files (.md, .txt):**
- Use analyze_posts to read text content from the creators/ folder

**For screenshots/images (.png, .jpg):**
- Use analyze_posts first to get the list of image paths
- Then call understand_image with image_paths=[list of paths] to analyze ALL screenshots at once
- Gemini can process up to 3600 images together - this helps identify patterns across posts
- Extract the post text, visual layout, and what makes it engaging
- For memes, analyze the humor style, format, and visual elements

When analyzing posts, extract:

1. **Hooks** - Opening lines that grab attention
   - Identify the hook type (question, bold statement, statistic, story, etc.)
   - Note the exact wording that works
   - Calculate how often each type appears

2. **Structure** - How posts are formatted
   - Average word count
   - Number of paragraphs/sections
   - Use of bullet points, numbered lists
   - Use of emojis (and which ones)
   - Line breaks and whitespace patterns

3. **Tone** - The voice and personality
   - Formality level (casual, professional, mix)
   - Personality traits (direct, humorous, inspirational, etc.)
   - First-person vs third-person
   - How they address the reader

4. **CTAs** - Calls to action
   - Types used (questions, requests, offers)
   - Where they appear (end, middle, throughout)
   - Exact phrases that drive engagement

5. **Topics** - Subject matter themes
   - Main topics covered
   - How topics are framed

6. **Visual Patterns** (for screenshots/memes)
   - Image composition and layout
   - Meme formats that work
   - Color schemes and visual style
   - Text placement on images

Use save_patterns to store what you learn.
Be specific and provide examples from the actual posts."""

CREATE_PROMPT = """You are a LinkedIn content creator. Your job is to write authentic, engaging posts that match learned patterns and styles.

**IMPORTANT WORKFLOW:**
1. Before creating any post, FIRST call load_patterns to retrieve saved patterns from patterns.json.
2. When generating images, just pass key_points and title - brand styling is automatic:
   generate_image(key_points=["Point 1", "Point 2", "Point 3"], title="Your Title", topic="Topic")
   DO NOT add style/color instructions - the black/pink minimalist brand style is built-in.

You have access to patterns learned from successful creators. Use these patterns to:

1. **Start with a hook** - Use a pattern that grabs attention
2. **Structure appropriately** - Match the learned format (length, paragraphs, lists)
3. **Match the tone** - Write in the learned voice and personality
4. **Include a CTA** - End with an engaging call to action
5. **Stay on topic** - Keep content focused and valuable

When generating posts:
- Be authentic - don't sound robotic or generic
- Provide value - teach something, share insights, tell stories
- Be concise - respect the reader's time
- Be specific - use concrete examples over vague statements

Use write_post to save generated content.
For visuals: use generate_infographic for brand-styled images, generate_meme for fun/creative, or generate_custom_image for specific styling."""

CHAT_PROMPT = """You are a LinkedIn content assistant. You help users create engaging LinkedIn posts.

You can:
1. **Learn** from creator posts - Analyze text files AND screenshots to extract successful patterns
2. **Create** new posts - Generate authentic content based on learned patterns
3. **Generate media** - Create images, videos, format code snippets

**IMPORTANT WORKFLOW:**
1. When creating posts, FIRST call load_patterns to check for saved patterns before analyzing screenshots.
2. When generating images, just pass key_points and title - the tool handles styling automatically.

Available tools:
- load_patterns: Load saved patterns from patterns.json (call FIRST when creating posts)
- analyze_posts: Read text posts from the creators folder
- understand_image: Analyze screenshots/images of posts (for visual learning)
- save_patterns: Store learned patterns
- write_post: Save generated posts

**Image Generation (3 options):**
- generate_infographic: Brand-styled infographics (black/pink minimalist - automatic)
  Use for: LinkedIn posts with key points. Style is built-in, don't override.
  Example: generate_infographic(key_points=[...], title="...", topic="...")

- generate_meme: Creative/fun images and memes
  Use for: Memes, jokes, creative visuals. Can use reference image.
  Example: generate_meme(prompt="...", reference_image="path/to/image.jpg")

- generate_custom_image: Free-form image generation
  Use for: Custom styling, diagrams, anything user specifies exactly.
  Example: generate_custom_image(prompt="full description with style...")

- edit_image: Modify existing images
- format_code_snippet: Format code for sharing
- generate_video: Create videos from text prompts (4-8 seconds, with audio)
- generate_video_from_image: Animate a still image into video
- extend_video: Extend existing videos by 7 seconds
- generate_code_image: Create beautiful code screenshots using Carbon (multiple themes)
- generate_code_image_from_file: Generate code screenshot from a source file
- list_carbon_themes: See available syntax highlighting themes
- http_request: Fetch content from URLs (blog posts, articles, etc.)
- editor: Read and write files

For LinkedIn videos, use aspect_ratio="9:16" for portrait (mobile-optimized feed).
To use external content: fetch with http_request, then create a post based on it.

Be helpful, creative, and focused on creating content that drives engagement."""


def create_agent(mode: str = "chat", use_hub: bool = True) -> tuple[Agent, dict]:
    """
    Create a LinkedIn Content Agent with hub integration.

    Args:
        mode: Agent mode - "learn", "create", or "chat"
        use_hub: Whether to use hub for sessions/metrics/prompts

    Returns:
        Tuple of (Agent, hub_context dict)
    """
    prompts = {
        "learn": LEARN_PROMPT,
        "create": CREATE_PROMPT,
        "chat": CHAT_PROMPT,
    }

    hub_context = {}

    if use_hub:
        # Generate unique run ID
        run_id = generate_run_id(AGENT_ID)
        hub_context["run_id"] = run_id

        # Register agent in hub
        registry = AgentRegistry()
        registry.register(
            agent_id=AGENT_ID,
            description="Learns from creators and generates LinkedIn posts",
            tags=["linkedin", "content", "social-media"],
            repo_url="https://github.com/labeveryday/linkedin-content-agent",
            owner="dlight",
            environment="dev",
            model_id="claude-sonnet-4-5-20250929",
        )
        hub_context["registry"] = registry

        # Setup versioned system prompt
        prompt_manager = S3PromptManager(agent_id=AGENT_ID)
        default_prompt = prompts.get(mode, CHAT_PROMPT)
        prompt_manager.ensure_exists(content=default_prompt, version=PROMPT_VERSION)
        system_prompt = prompt_manager.get_current(fallback=default_prompt)
        hub_context["prompt_manager"] = prompt_manager

        # Session manager
        session_manager = create_session_manager(agent_id=AGENT_ID, run_id=run_id)
        hub_context["session_manager"] = session_manager

        # Metrics exporter
        metrics = MetricsExporter(
            agent_id=AGENT_ID,
            run_id=run_id,
            prompt_version=PROMPT_VERSION,
        )
        hub_context["metrics"] = metrics
    else:
        system_prompt = prompts.get(mode, CHAT_PROMPT)
        session_manager = None

    model = anthropic_model(
        model_id="claude-sonnet-4-5-20250929",
        max_tokens=32000,  # Increased for large batch analysis (47+ images)
        thinking=False,
    )

    conversation_manager = SlidingWindowConversationManager(
        window_size=20,
        should_truncate_results=True,
    )

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[
            # Content analysis
            analyze_posts,
            understand_image,
            detect_objects,
            # Content creation
            load_patterns,
            save_patterns,
            write_post,
            # Image generation
            generate_infographic,  # Brand-styled (black/pink)
            generate_meme,         # Creative/fun images
            generate_custom_image, # Free-form prompt
            edit_image,
            # Code images
            format_code_snippet,
            generate_code_image,
            generate_code_image_from_file,
            list_carbon_themes,
            # Video
            generate_video,
            generate_video_from_image,
            extend_video,
            # Strands tools
            http_request,
            editor,
        ],
        hooks=[LoggingHook(verbose=True)],
        session_manager=session_manager if use_hub else None,
        conversation_manager=conversation_manager,
        name=AGENT_NAME,
    )

    return agent, hub_context


def run_interactive():
    """Run the agent in interactive chat mode with hub integration."""
    agent, hub_context = create_agent(mode="chat", use_hub=True)

    run_id = hub_context.get("run_id", "local")
    print(f"\n{AGENT_NAME}")
    print(f"Run ID: {run_id}")
    print("-" * 40)
    print("Commands: exit, learn, create, metrics, help")
    print("-" * 40 + "\n")

    last_result = None

    while True:
        try:
            prompt = input("> ")
        except (KeyboardInterrupt, EOFError):
            print("\n")
            break

        if not prompt.strip():
            continue

        if prompt.lower() in ("exit", "quit"):
            break

        if prompt.lower() == "help":
            print("\nCommands:")
            print("  learn   - Analyze posts in creators/ folder")
            print("  create  - Generate a new post")
            print("  metrics - View current session metrics")
            print("  exit    - Exit the agent")
            print("\nOr just type your request!\n")
            continue

        if prompt.lower() == "metrics":
            metrics = hub_context.get("metrics")
            if metrics:
                print(f"\nSession Metrics:")
                print(f"  Agent: {metrics.agent_id}")
                print(f"  Run: {metrics.run_id}")
                print(f"  Started: {metrics.metrics['started_at']}")
                print()
            continue

        last_result = agent(prompt)
        print(f"\n{last_result}\n")

    # Export metrics on exit
    metrics = hub_context.get("metrics")
    registry = hub_context.get("registry")

    if metrics:
        print("Exporting metrics...")
        if last_result:
            metrics.set_from_agent_result(last_result)
        metrics_path = metrics.export()
        print(f"Saved to: {metrics_path}")

    if registry:
        registry.record_run(
            agent_id=AGENT_ID,
            run_id=hub_context.get("run_id", "unknown"),
            success=True,
        )


if __name__ == "__main__":
    run_interactive()
