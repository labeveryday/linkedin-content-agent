"""Model providers for LinkedIn Content Agent.

Supports Anthropic (Claude), Gemini, and OpenAI models.
"""

import os
from dotenv import load_dotenv
from strands.models.anthropic import AnthropicModel
from strands.models.gemini import GeminiModel
from strands.models.openai import OpenAIModel

load_dotenv()


def anthropic_model(
    api_key: str = os.getenv("ANTHROPIC_API_KEY"),
    model_id: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 4000,
    temperature: float = 1,
    thinking: bool = False,
    budget_tokens: int = 1024,
) -> AnthropicModel:
    """
    Create an Anthropic Claude model for content generation.

    Args:
        api_key: Anthropic API key
        model_id: Model to use (default: claude-sonnet-4-5-20250929)
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        thinking: Enable extended thinking
        budget_tokens: Token budget for thinking

    Available models:
    - claude-sonnet-4-5-20250929: Best for creative writing (200k context)
    - claude-haiku-4-5-20251001: Fast, cost-effective (200k context)
    """
    if thinking:
        if budget_tokens >= max_tokens:
            raise ValueError("Budget tokens cannot be greater than max tokens")
        thinking_config = {"type": "enabled", "budget_tokens": budget_tokens}
    else:
        thinking_config = {"type": "disabled"}

    return AnthropicModel(
        client_args={"api_key": api_key},
        max_tokens=max_tokens,
        model_id=model_id,
        params={"temperature": temperature, "thinking": thinking_config},
    )


def gemini_model(
    api_key: str = os.getenv("GOOGLE_API_KEY"),
    model_id: str = "gemini-2.5-flash-preview-05-20",
    max_tokens: int = 8192,
    temperature: float = 1,
) -> GeminiModel:
    """
    Create a Gemini model (used for image/video generation tools).

    Args:
        api_key: Google API key
        model_id: Model to use
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Available models:
    - gemini-2.5-flash-preview-05-20: Fast, multimodal
    - gemini-2.5-pro-preview-06-05: Advanced reasoning
    """
    return GeminiModel(
        client_args={"api_key": api_key},
        model_id=model_id,
        params={
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        },
    )


def openai_model(
    api_key: str = os.getenv("OPENAI_API_KEY"),
    model_id: str = "gpt-4o",
    max_tokens: int = 4000,
    temperature: float = 1,
) -> OpenAIModel:
    """
    Create an OpenAI model.

    Args:
        api_key: OpenAI API key
        model_id: Model to use
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
    """
    return OpenAIModel(
        client_args={"api_key": api_key},
        model_id=model_id,
        params={
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        },
    )
