"""
Agent Registry - Track all agents with metadata.

Auto-registers agents on first run, stores in S3 for discovery.
"""

import json
import time
from typing import Optional

from .config import get_config


class AgentRegistry:
    """
    Registry for tracking all agents.

    Usage:
        registry = AgentRegistry()

        # Auto-register on first run
        registry.register(
            agent_id="linkedin-agent",
            description="Learns from creators and generates LinkedIn posts",
            tags=["linkedin", "content"]
        )

        # List all agents
        agents = registry.list_agents()
    """

    def __init__(self):
        self.config = get_config()
        self._local_registry = self.config.local_dir / "registry.json"
        self._cache: dict | None = None

    def register(
        self,
        agent_id: str,
        description: str | None = None,
        tags: list[str] | None = None,
        system_prompt_key: str | None = None,
        repo_url: str | None = None,
        owner: str | None = None,
        environment: str | None = None,
        model_id: str | None = None,
        update_if_exists: bool = False,
    ) -> dict:
        """
        Register an agent in the registry.

        Args:
            agent_id: Unique identifier for the agent
            description: Human-readable description
            tags: List of tags for categorization
            system_prompt_key: S3 key to the system prompt
            repo_url: URL to the agent's source code repository
            owner: Owner/maintainer of the agent
            environment: Deployment environment (dev, staging, prod)
            model_id: Model ID the agent uses
            update_if_exists: Whether to update existing entry

        Returns:
            The agent entry
        """
        registry = self._load_registry()

        existing = registry["agents"].get(agent_id)
        if existing and not update_if_exists:
            # Already registered, return existing
            return existing

        # Create or update entry
        entry = existing or {
            "agent_id": agent_id,
            "created_at": time.time(),
        }

        entry["updated_at"] = time.time()

        if description:
            entry["description"] = description
        if tags:
            entry["tags"] = tags
        if system_prompt_key:
            entry["system_prompt_key"] = system_prompt_key
        if repo_url:
            entry["repo_url"] = repo_url
        if owner:
            entry["owner"] = owner
        if environment:
            entry["environment"] = environment
        if model_id:
            entry["model_id"] = model_id

        # Set default prompt key if not specified
        if "system_prompt_key" not in entry:
            entry["system_prompt_key"] = f"system_prompts/{agent_id}/current.txt"

        registry["agents"][agent_id] = entry
        self._save_registry(registry)

        return entry

    def get_agent(self, agent_id: str) -> Optional[dict]:
        """Get an agent's registry entry."""
        registry = self._load_registry()
        return registry["agents"].get(agent_id)

    def list_agents(self, tag: str | None = None) -> list[dict]:
        """
        List all registered agents.

        Args:
            tag: Optional tag to filter by

        Returns:
            List of agent entries
        """
        registry = self._load_registry()
        agents = list(registry["agents"].values())

        if tag:
            agents = [a for a in agents if tag in a.get("tags", [])]

        return sorted(agents, key=lambda x: x.get("created_at", 0))

    def update_agent(
        self,
        agent_id: str,
        description: str | None = None,
        tags: list[str] | None = None,
        repo_url: str | None = None,
        owner: str | None = None,
        environment: str | None = None,
        model_id: str | None = None,
    ) -> Optional[dict]:
        """Update an existing agent's metadata."""
        return self.register(
            agent_id=agent_id,
            description=description,
            tags=tags,
            repo_url=repo_url,
            owner=owner,
            environment=environment,
            model_id=model_id,
            update_if_exists=True,
        )

    def record_run(self, agent_id: str, run_id: str, success: bool) -> None:
        """Record that an agent had a run."""
        registry = self._load_registry()

        agent = registry["agents"].get(agent_id)
        if not agent:
            return

        # Update run stats
        if "run_stats" not in agent:
            agent["run_stats"] = {"total_runs": 0, "successful_runs": 0}

        agent["run_stats"]["total_runs"] += 1
        if success:
            agent["run_stats"]["successful_runs"] += 1

        agent["last_run_at"] = time.time()
        agent["last_run_id"] = run_id

        self._save_registry(registry)

    def _load_registry(self) -> dict:
        """Load registry from S3 or local cache."""
        if self._cache is not None:
            return self._cache

        # Try S3 first
        if self.config.use_s3:
            try:
                import boto3
                from botocore.exceptions import ClientError

                s3 = boto3.client("s3", region_name=self.config.region)

                try:
                    response = s3.get_object(
                        Bucket=self.config.bucket,
                        Key=self.config.registry_key,
                    )
                    self._cache = json.loads(response["Body"].read().decode("utf-8"))

                    # Also save locally for offline access
                    self._save_local_registry(self._cache)

                    return self._cache
                except ClientError as e:
                    if e.response["Error"]["Code"] != "NoSuchKey":
                        raise
            except Exception as e:
                print(f"Warning: Could not load registry from S3: {e}")

        # Try local
        if self._local_registry.exists():
            with open(self._local_registry) as f:
                self._cache = json.load(f)
            return self._cache

        # Initialize empty registry
        self._cache = {"agents": {}, "created_at": time.time()}
        return self._cache

    def _save_registry(self, registry: dict) -> None:
        """Save registry to S3 and local."""
        registry["updated_at"] = time.time()
        self._cache = registry

        # Save locally first
        self._save_local_registry(registry)

        # Try S3
        if self.config.use_s3:
            try:
                import boto3

                s3 = boto3.client("s3", region_name=self.config.region)
                s3.put_object(
                    Bucket=self.config.bucket,
                    Key=self.config.registry_key,
                    Body=json.dumps(registry, indent=2),
                    ContentType="application/json",
                )
            except Exception as e:
                print(f"Warning: Could not save registry to S3: {e}")
                self._queue_for_sync()

    def _save_local_registry(self, registry: dict) -> None:
        """Save registry to local file."""
        with open(self._local_registry, "w") as f:
            json.dump(registry, f, indent=2)

    def _queue_for_sync(self) -> None:
        """Queue registry for later S3 sync."""
        sync_queue = self.config.local_dir / "registry_sync_pending"
        sync_queue.touch()

    @classmethod
    def sync_if_pending(cls) -> bool:
        """Sync registry to S3 if there's a pending sync."""
        config = get_config()
        sync_pending = config.local_dir / "registry_sync_pending"

        if not sync_pending.exists():
            return False

        if not config.use_s3:
            return False

        registry = cls()
        try:
            import boto3

            s3 = boto3.client("s3", region_name=config.region)

            # Load local and upload
            if registry._local_registry.exists():
                with open(registry._local_registry) as f:
                    data = json.load(f)

                s3.put_object(
                    Bucket=config.bucket,
                    Key=config.registry_key,
                    Body=json.dumps(data, indent=2),
                    ContentType="application/json",
                )

                sync_pending.unlink()
                return True
        except Exception:
            pass

        return False
