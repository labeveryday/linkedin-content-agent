"""Pattern storage for learned creator styles."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class PatternStore:
    """JSON-based storage for learned content patterns."""

    def __init__(self, storage_path: str = "patterns/patterns.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        """Load patterns from storage."""
        if not self.storage_path.exists():
            return self._empty_patterns()

        with open(self.storage_path, "r") as f:
            return json.load(f)

    def save(self, patterns: dict) -> None:
        """Save patterns to storage."""
        patterns["updated_at"] = datetime.now().isoformat()
        with open(self.storage_path, "w") as f:
            json.dump(patterns, f, indent=2)

    def update(self, new_patterns: dict, sources: list[str]) -> dict:
        """Update patterns with new analysis, merging with existing."""
        current = self.load()

        # Update metadata
        current["updated_at"] = datetime.now().isoformat()
        current["sources"] = list(set(current.get("sources", []) + sources))

        # Merge patterns
        if "patterns" not in current:
            current["patterns"] = {}

        for key, value in new_patterns.items():
            if key in current["patterns"] and isinstance(value, list):
                # Merge lists (hooks, ctas, topics)
                existing = current["patterns"][key]
                current["patterns"][key] = self._merge_lists(existing, value)
            elif key in current["patterns"] and isinstance(value, dict):
                # Merge dicts (structure, tone)
                current["patterns"][key].update(value)
            else:
                current["patterns"][key] = value

        self.save(current)
        return current

    def _merge_lists(self, existing: list, new: list) -> list:
        """Merge two lists, avoiding duplicates based on 'example' key."""
        seen = {item.get("example") for item in existing if isinstance(item, dict)}
        for item in new:
            if isinstance(item, dict):
                if item.get("example") not in seen:
                    existing.append(item)
                    seen.add(item.get("example"))
            elif item not in existing:
                existing.append(item)
        return existing

    def clear(self) -> None:
        """Clear all stored patterns."""
        self.save(self._empty_patterns())

    def get_summary(self) -> Optional[str]:
        """Get a human-readable summary of stored patterns."""
        patterns = self.load()
        if not patterns.get("patterns"):
            return None

        p = patterns["patterns"]
        lines = [
            f"Sources: {len(patterns.get('sources', []))} posts analyzed",
            f"Last updated: {patterns.get('updated_at', 'Never')}",
            "",
        ]

        if "hooks" in p:
            lines.append(f"Hooks: {len(p['hooks'])} patterns")
        if "structure" in p:
            lines.append(f"Avg length: {p['structure'].get('avg_length', 'N/A')} words")
        if "tone" in p:
            lines.append(f"Tone: {p['tone'].get('formality', 'N/A')}")
        if "ctas" in p:
            lines.append(f"CTAs: {len(p['ctas'])} patterns")
        if "topics" in p:
            lines.append(f"Topics: {', '.join(p['topics'][:5])}")

        return "\n".join(lines)

    def _empty_patterns(self) -> dict:
        """Return empty pattern structure."""
        return {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "sources": [],
            "patterns": {},
        }
