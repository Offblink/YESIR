"""Event sinks: where agent turns emit their stream (console, web NDJSON, or any callable)."""

import sys
from collections.abc import Callable
from typing import Any, ClassVar, Protocol

EmitFn = Callable[[str, Any], None]


class Sink(Protocol):
    def emit(self, event_type: str, content: Any) -> None: ...


class FnSink:
    """Adapts a plain callable into a Sink."""

    def __init__(self, fn: EmitFn) -> None:
        self._fn = fn

    def emit(self, event_type: str, content: Any = None) -> None:
        self._fn(event_type, content)


class NullSink:
    def emit(self, event_type: str, content: Any = None) -> None:
        pass


class ConsoleSink:
    """Terminal output, mirroring the PowerShell original's formatting."""

    _COLORS: ClassVar[dict] = {
        "reasoning": "\033[90m",
        "tool": "\033[33m",
        "tool_args": "\033[93m",
        "result": "\033[90m",
        "error": "\033[31m",
    }
    _RESET = "\033[0m"

    def emit(self, event_type: str, content: Any = None) -> None:
        if event_type == "text":
            sys.stdout.write(str(content))
            sys.stdout.flush()
        elif event_type == "tool":
            args = content.get("args", "")
            sys.stdout.write(f"  [{content['name']}] {args}")
            sys.stdout.flush()
        elif event_type == "tool_result":
            print(f"\n{content['content']}")
        elif event_type == "reasoning":
            sys.stdout.write(f"{self._COLORS['reasoning']}{content}{self._RESET}")
            sys.stdout.flush()
        elif event_type == "error":
            print(f"\n[ERROR: {content}]")
        # newline / reasoning_start / reasoning_end: console-only cosmetics, ignored here
