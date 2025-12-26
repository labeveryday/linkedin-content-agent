"""
Logging Hook - Log tool invocations before and after execution.
"""

import json
from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent, AfterToolCallEvent


class LoggingHook(HookProvider):
    """
    Hook that logs tool invocations before and after execution.

    Usage:
        agent = Agent(hooks=[LoggingHook()])
    """

    def __init__(self, verbose: bool = True, show_results: bool = True):
        """
        Initialize the logging hook.

        Args:
            verbose: If True, print full input parameters. If False, just tool name.
            show_results: If True, print tool results (errors always shown).
        """
        self.tool_count = 0
        self.verbose = verbose
        self.show_results = show_results

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.log_start)
        registry.add_callback(AfterToolCallEvent, self.log_end)

    def log_start(self, event: BeforeToolCallEvent) -> None:
        self.tool_count += 1
        tool_name = event.tool_use.get("name", "unknown")
        tool_input = event.tool_use.get("input", {})

        print("=" * 60)
        print(f"Tool #{self.tool_count}: {tool_name}")
        print(f"Agent: {event.agent.name}")

        if self.verbose and tool_input:
            # Truncate long inputs (like image_paths with 47 items)
            display_input = {}
            for key, value in tool_input.items():
                if isinstance(value, list) and len(value) > 5:
                    display_input[key] = f"[{len(value)} items]"
                elif isinstance(value, str) and len(value) > 500:
                    display_input[key] = value[:500] + "..."
                else:
                    display_input[key] = value

            print("Input:")
            formatted_input = json.dumps(display_input, indent=2)
            for line in formatted_input.split("\n"):
                print(f"  {line}")

        print("-" * 60)

    def log_end(self, event: AfterToolCallEvent) -> None:
        tool_name = event.tool_use.get("name", "unknown")
        result = event.result

        # Extract result content
        result_text = None
        is_error = False

        if isinstance(result, dict):
            content = result.get("content", [])
            if content and isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        result_text = item["text"]
                        break
            # Check for error indicators
            if "error" in str(result_text or "").lower():
                is_error = True

        # Always show errors, optionally show success
        if is_error or self.show_results:
            status = "❌ ERROR" if is_error else "✓ Done"
            print(f"{status}: {tool_name}")

            if result_text and (is_error or self.verbose):
                # Truncate long results
                if len(result_text) > 500:
                    result_text = result_text[:500] + "..."
                print(f"Result: {result_text}")

        print("=" * 60)
