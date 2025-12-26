"""
Metrics Export - Save run metrics to S3 or local storage.

Supports offline-first workflow: saves locally, syncs to S3 when available.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import get_config


class MetricsExporter:
    """
    Export agent run metrics to S3 or local storage.

    Usage:
        exporter = MetricsExporter(agent_id="linkedin-agent", run_id="linkedin-agent_20241215")
        exporter.set("posts_generated", 5)
        exporter.set("success_rate", 0.95)
        exporter.export()  # Saves to S3 or local
    """

    def __init__(
        self,
        agent_id: str,
        run_id: str,
        prompt_version: str | None = None,
    ):
        self.agent_id = agent_id
        self.run_id = run_id
        self.prompt_version = prompt_version
        self.config = get_config()

        # Initialize metrics
        self.metrics: dict[str, Any] = {
            "agent_id": agent_id,
            "run_id": run_id,
            "prompt_version": prompt_version,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "timing": {},
            "stats": {},
            "custom": {},
        }

        self._exported = False

    def set(self, key: str, value: Any, category: str = "custom") -> None:
        """
        Set a metric value.

        Args:
            key: Metric name
            value: Metric value
            category: One of "timing", "stats", "custom"
        """
        if category in ("timing", "stats", "custom"):
            self.metrics[category][key] = value
        else:
            self.metrics[key] = value

    def set_timing(self, key: str, value: float) -> None:
        """Set a timing metric (seconds)."""
        self.metrics["timing"][key] = value

    def set_stats(self, key: str, value: Any) -> None:
        """Set a stats metric."""
        self.metrics["stats"][key] = value

    def set_from_agent_result(self, result: Any) -> None:
        """
        Extract metrics from a Strands AgentResult.

        Args:
            result: The AgentResult from agent invocation
        """
        if not hasattr(result, "metrics"):
            return

        metrics = result.metrics

        # Token usage
        if hasattr(metrics, "accumulated_usage"):
            usage = metrics.accumulated_usage
            self.set_stats("input_tokens", usage.get("inputTokens", 0))
            self.set_stats("output_tokens", usage.get("outputTokens", 0))
            self.set_stats("total_tokens", usage.get("totalTokens", 0))

        # Timing
        if hasattr(metrics, "accumulated_metrics"):
            acc_metrics = metrics.accumulated_metrics
            self.set_timing("latency_ms", acc_metrics.get("latencyMs", 0))

        if hasattr(metrics, "cycle_durations"):
            self.set_timing("total_duration", sum(metrics.cycle_durations))
            self.set_stats("total_cycles", len(metrics.cycle_durations))

        # Tool metrics
        if hasattr(metrics, "tool_metrics"):
            tool_summary = {}
            for tool_name, tool_data in metrics.tool_metrics.items():
                tool_summary[tool_name] = {
                    "call_count": getattr(tool_data, "call_count", 0),
                    "success_count": getattr(tool_data, "success_count", 0),
                    "error_count": getattr(tool_data, "error_count", 0),
                }
            self.set_stats("tool_usage", tool_summary)

    def export(self) -> Path | str:
        """
        Export metrics to storage.

        Returns:
            Path (local) or S3 key where metrics were saved
        """
        self.metrics["completed_at"] = datetime.now().isoformat()

        # Calculate duration if we have timing data
        if self.metrics.get("started_at") and self.metrics.get("completed_at"):
            start = datetime.fromisoformat(self.metrics["started_at"])
            end = datetime.fromisoformat(self.metrics["completed_at"])
            self.metrics["timing"]["total_runtime_seconds"] = (end - start).total_seconds()

        # Try S3 first
        if self.config.use_s3:
            try:
                s3_key = self._export_to_s3()
                self._exported = True
                return s3_key
            except Exception as e:
                print(f"Warning: S3 export failed ({e}), saving locally")

        # Local fallback
        local_path = self._export_to_local()
        self._exported = True

        # Queue for sync later if S3 was intended
        if self.config.use_s3:
            self._queue_for_sync(local_path)

        return local_path

    def _export_to_s3(self) -> str:
        """Export metrics to S3."""
        import boto3

        s3 = boto3.client("s3", region_name=self.config.region)

        # Organize by date: metrics/2024-12-15/run_id.json
        date_str = datetime.now().strftime("%Y-%m-%d")
        s3_key = f"{self.config.metrics_prefix}{date_str}/{self.run_id}.json"

        s3.put_object(
            Bucket=self.config.bucket,
            Key=s3_key,
            Body=json.dumps(self.metrics, indent=2, default=str),
            ContentType="application/json",
        )

        return s3_key

    def _export_to_local(self) -> Path:
        """Export metrics to local file."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        date_dir = self.config.local_metrics_dir / date_str
        date_dir.mkdir(exist_ok=True)

        local_path = date_dir / f"{self.run_id}.json"

        with open(local_path, "w") as f:
            json.dump(self.metrics, f, indent=2, default=str)

        return local_path

    def _queue_for_sync(self, local_path: Path) -> None:
        """Queue a local file for later S3 sync."""
        sync_queue = self.config.local_dir / "sync_queue.txt"
        with open(sync_queue, "a") as f:
            f.write(f"{local_path}\n")

    @classmethod
    def sync_pending(cls) -> int:
        """
        Sync any pending local metrics to S3.

        Returns:
            Number of files synced
        """
        config = get_config()
        sync_queue = config.local_dir / "sync_queue.txt"

        if not sync_queue.exists():
            return 0

        if not config.use_s3:
            return 0

        try:
            import boto3
            s3 = boto3.client("s3", region_name=config.region)
        except Exception:
            return 0

        synced = 0
        remaining = []

        with open(sync_queue, "r") as f:
            paths = [line.strip() for line in f if line.strip()]

        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                continue

            try:
                with open(path, "r") as f:
                    metrics = json.load(f)

                # Upload to S3
                date_str = path.parent.name
                run_id = path.stem
                s3_key = f"{config.metrics_prefix}{date_str}/{run_id}.json"

                s3.put_object(
                    Bucket=config.bucket,
                    Key=s3_key,
                    Body=json.dumps(metrics, indent=2, default=str),
                    ContentType="application/json",
                )

                synced += 1
            except Exception:
                remaining.append(path_str)

        # Update queue with remaining items
        if remaining:
            with open(sync_queue, "w") as f:
                f.write("\n".join(remaining) + "\n")
        else:
            sync_queue.unlink(missing_ok=True)

        return synced
