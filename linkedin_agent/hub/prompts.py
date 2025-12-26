"""
System Prompt Management - Versioned prompt storage with S3 backend.

Caches prompts locally to avoid fetching on every run.
Only fetches from S3 when explicitly requested or cache expires.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from .config import get_config


class S3PromptManager:
    """
    Manage system prompts with S3 storage and local caching.

    Usage:
        manager = S3PromptManager(agent_id="linkedin-agent")

        # First time: upload prompt
        manager.ensure_exists(content=PROMPT, version="v1")

        # Get current prompt (cached)
        prompt = manager.get_current()

        # Update prompt
        manager.set(content=NEW_PROMPT, version="v2")
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.config = get_config()

        # Local cache directory for this agent
        self.cache_dir = self.config.local_prompts_dir / agent_id
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._cache_file = self.cache_dir / "current.txt"
        self._cache_meta = self.cache_dir / "cache_meta.json"

    def get_current(
        self,
        force_refresh: bool = False,
        fallback: str | Path | None = None,
    ) -> str:
        """
        Get the current system prompt.

        Args:
            force_refresh: Force fetch from S3 even if cached
            fallback: Fallback content or file path if S3 unavailable

        Returns:
            The system prompt content
        """
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached = self._get_from_cache()
            if cached is not None:
                return cached

        # Try S3
        if self.config.use_s3:
            try:
                content = self._fetch_from_s3("current.txt")
                if content:
                    self._save_to_cache(content)
                    return content
            except Exception as e:
                print(f"Warning: Could not fetch prompt from S3: {e}")

        # Try local cache (even if expired)
        cached = self._get_from_cache(ignore_ttl=True)
        if cached is not None:
            return cached

        # Fallback
        if fallback:
            if isinstance(fallback, Path) or (isinstance(fallback, str) and Path(fallback).exists()):
                with open(fallback, "r") as f:
                    return f.read()
            return fallback

        raise FileNotFoundError(
            f"No system prompt found for agent '{self.agent_id}'. "
            "Use ensure_exists() or set() to create one."
        )

    def ensure_exists(
        self,
        content: str,
        version: str = "v1",
    ) -> str:
        """
        Ensure a prompt version exists, upload if not.

        Args:
            content: The prompt content
            version: Version string (e.g., "v1", "v2")

        Returns:
            The version that's now current
        """
        # Check if this version already exists in S3
        if self.config.use_s3:
            try:
                existing = self._fetch_from_s3(f"{version}.txt")
                if existing:
                    # Version exists, check if it's current
                    current = self._fetch_from_s3("current.txt")
                    if not current:
                        # No current set, make this one current
                        self._upload_to_s3("current.txt", existing)
                    return version
            except Exception:
                pass

        # Check local
        local_version = self.cache_dir / f"{version}.txt"
        if local_version.exists():
            # Already exists locally
            local_content = local_version.read_text()

            if not self._cache_file.exists():
                # Make it current locally
                self._save_to_cache(local_content)

            # Also upload to S3 if enabled and not already there
            if self.config.use_s3:
                try:
                    existing_in_s3 = self._fetch_from_s3(f"{version}.txt")
                    if not existing_in_s3:
                        print(f"  Syncing local prompt {version} to S3...")
                        self._upload_to_s3(f"{version}.txt", local_content)
                        self._upload_to_s3("current.txt", local_content)
                        self._update_versions_manifest(version, None)
                        print("  Synced to S3")
                except Exception as e:
                    print(f"  Warning: Could not sync to S3: {e}")

            return version

        # Doesn't exist anywhere, create it
        self.set(content=content, version=version, make_current=True)
        return version

    def set(
        self,
        content: str,
        version: str,
        make_current: bool = True,
        note: str | None = None,
    ) -> None:
        """
        Upload a new prompt version.

        Args:
            content: The prompt content
            version: Version string (e.g., "v1", "v2")
            make_current: Whether to set this as the current version
            note: Optional note about this version
        """
        # Save locally first
        local_version = self.cache_dir / f"{version}.txt"
        local_version.write_text(content)

        # Save version metadata
        self._save_version_meta(version, note)

        # Upload to S3 if enabled
        if self.config.use_s3:
            try:
                print(f"  Uploading prompt {version} to S3...")
                self._upload_to_s3(f"{version}.txt", content)

                if make_current:
                    self._upload_to_s3("current.txt", content)
                    self._update_versions_manifest(version, note)
            except Exception as e:
                print(f"Warning: Could not upload prompt to S3: {e}")
                self._queue_for_sync(version)

        # Update local cache
        if make_current:
            self._save_to_cache(content)

    def get_version(self, version: str) -> str:
        """Get a specific version of the prompt."""
        # Check local first
        local_version = self.cache_dir / f"{version}.txt"
        if local_version.exists():
            return local_version.read_text()

        # Try S3
        if self.config.use_s3:
            content = self._fetch_from_s3(f"{version}.txt")
            if content:
                # Cache it locally
                local_version.write_text(content)
                return content

        raise FileNotFoundError(f"Prompt version '{version}' not found")

    def list_versions(self) -> list[dict]:
        """List all available versions with metadata."""
        versions = []

        # Check local versions
        for f in self.cache_dir.glob("v*.txt"):
            version = f.stem
            meta_file = self.cache_dir / f"{version}_meta.json"
            meta = {}
            if meta_file.exists():
                with open(meta_file) as mf:
                    meta = json.load(mf)

            versions.append({
                "version": version,
                "local": True,
                "note": meta.get("note"),
                "created_at": meta.get("created_at"),
            })

        return sorted(versions, key=lambda x: x["version"])

    def _get_from_cache(self, ignore_ttl: bool = False) -> Optional[str]:
        """Get prompt from local cache."""
        if not self._cache_file.exists():
            return None

        # Check TTL
        if not ignore_ttl and self._cache_meta.exists():
            with open(self._cache_meta) as f:
                meta = json.load(f)

            cached_at = meta.get("cached_at", 0)
            if time.time() - cached_at > self.config.prompt_cache_ttl_seconds:
                return None  # Cache expired

        return self._cache_file.read_text()

    def _save_to_cache(self, content: str) -> None:
        """Save prompt to local cache."""
        self._cache_file.write_text(content)

        # Save cache metadata
        with open(self._cache_meta, "w") as f:
            json.dump({
                "cached_at": time.time(),
                "content_hash": hashlib.md5(content.encode()).hexdigest(),
            }, f)

    def _save_version_meta(self, version: str, note: str | None) -> None:
        """Save metadata for a version."""
        meta_file = self.cache_dir / f"{version}_meta.json"
        with open(meta_file, "w") as f:
            json.dump({
                "version": version,
                "note": note,
                "created_at": time.time(),
            }, f)

    def _fetch_from_s3(self, key: str) -> Optional[str]:
        """Fetch a prompt file from S3."""
        import boto3
        from botocore.exceptions import ClientError

        s3 = boto3.client("s3", region_name=self.config.region)
        s3_key = f"{self.config.prompts_prefix}{self.agent_id}/{key}"

        try:
            response = s3.get_object(Bucket=self.config.bucket, Key=s3_key)
            return response["Body"].read().decode("utf-8")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def _upload_to_s3(self, key: str, content: str) -> None:
        """Upload a prompt file to S3."""
        import boto3

        s3 = boto3.client("s3", region_name=self.config.region)
        s3_key = f"{self.config.prompts_prefix}{self.agent_id}/{key}"

        s3.put_object(
            Bucket=self.config.bucket,
            Key=s3_key,
            Body=content.encode("utf-8"),
            ContentType="text/plain",
        )

    def _update_versions_manifest(self, version: str, note: str | None) -> None:
        """Update the versions manifest in S3."""
        import boto3
        from botocore.exceptions import ClientError

        s3 = boto3.client("s3", region_name=self.config.region)
        manifest_key = f"{self.config.prompts_prefix}{self.agent_id}/versions.json"

        # Try to fetch existing manifest
        manifest = {"versions": [], "current": version}
        try:
            response = s3.get_object(Bucket=self.config.bucket, Key=manifest_key)
            manifest = json.loads(response["Body"].read().decode("utf-8"))
        except ClientError:
            pass

        # Add/update version
        manifest["current"] = version
        existing = next((v for v in manifest["versions"] if v["version"] == version), None)
        if existing:
            existing["note"] = note
            existing["updated_at"] = time.time()
        else:
            manifest["versions"].append({
                "version": version,
                "note": note,
                "created_at": time.time(),
            })

        # Upload updated manifest
        s3.put_object(
            Bucket=self.config.bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, indent=2),
            ContentType="application/json",
        )

    def _queue_for_sync(self, version: str) -> None:
        """Queue a version for later S3 sync."""
        sync_queue = self.config.local_dir / "prompt_sync_queue.txt"
        with open(sync_queue, "a") as f:
            f.write(f"{self.agent_id}:{version}\n")
