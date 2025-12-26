"""
Hub Configuration - Load settings from environment variables.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HubConfig:
    """
    Configuration for Agent Hub.

    Loads from environment variables with sensible defaults.

    Environment Variables:
        USE_S3: Enable S3 storage (default: false)
        AGENT_HUB_BUCKET: S3 bucket name
        AGENT_HUB_REGION: AWS region (default: us-east-1)
        AGENT_HUB_LOCAL_DIR: Local fallback directory
    """

    # S3 settings
    use_s3: bool = field(default_factory=lambda: os.getenv("USE_S3", "false").lower() == "true")
    bucket: str = field(default_factory=lambda: os.getenv("AGENT_HUB_BUCKET", ""))
    region: str = field(default_factory=lambda: os.getenv("AGENT_HUB_REGION", "us-east-1"))

    # S3 prefixes (no trailing slash - S3SessionManager adds its own)
    sessions_prefix: str = "sessions"
    metrics_prefix: str = "metrics/"
    prompts_prefix: str = "system_prompts/"
    registry_key: str = "registry.json"

    # Local fallback
    local_dir: Path = field(default_factory=lambda: Path(os.getenv("AGENT_HUB_LOCAL_DIR", "./.agent_hub")))

    # Cache settings
    prompt_cache_ttl_seconds: int = 3600  # 1 hour

    def __post_init__(self):
        """Validate configuration."""
        if self.use_s3 and not self.bucket:
            raise ValueError("AGENT_HUB_BUCKET must be set when USE_S3=true")

        # Ensure local directory exists
        self.local_dir.mkdir(parents=True, exist_ok=True)
        (self.local_dir / "sessions").mkdir(exist_ok=True)
        (self.local_dir / "metrics").mkdir(exist_ok=True)
        (self.local_dir / "prompts").mkdir(exist_ok=True)

    @property
    def local_sessions_dir(self) -> Path:
        return self.local_dir / "sessions"

    @property
    def local_metrics_dir(self) -> Path:
        return self.local_dir / "metrics"

    @property
    def local_prompts_dir(self) -> Path:
        return self.local_dir / "prompts"

    def s3_key(self, prefix: str, *parts: str) -> str:
        """Build S3 key from prefix and parts."""
        return prefix + "/".join(parts)


# Global config instance (can be overridden)
_config: HubConfig | None = None


def get_config() -> HubConfig:
    """Get or create the global hub configuration."""
    global _config
    if _config is None:
        _config = HubConfig()
    return _config


def set_config(config: HubConfig) -> None:
    """Override the global hub configuration."""
    global _config
    _config = config
