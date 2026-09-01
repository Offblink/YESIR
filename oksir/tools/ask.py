"""ask_user tool (L1 only): the Inquire mechanism.

Emits an `ask` event on the turn sink, then blocks the calling agent thread
until the UI answers via POST /answer (resolve_ask) or the timeout expires.
"""

import threading
import time
import uuid

from oksir.agent import BoundTool
from oksir.events import Sink

ASK_TIMEOUT_S = 300
HEARTBEAT_S = 15

ASK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Ask the user a question and wait for their answer. Only the orchestrator can"
            " ask; use it when a decision genuinely needs the user (approach choice,"
            " confirmation before something hard to undo). Returns 'USER: <answer>'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to ask"},
                "options": {
                    "type": "array",
                    "description": "Optional choices the user can pick from",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["label"],
                    },
                },
                "allow_custom": {
                    "type": "boolean",
                    "description": "Whether the user may type a free-form answer (default true)",
                },
            },
            "required": ["question"],
        },
    },
}

# ask id -> {"event": Event, "value": str | None}
_pending: dict[str, dict] = {}
_lock = threading.Lock()


def resolve_ask(ask_id: str, value: str) -> bool:
    """Wake a pending ask (called by POST /answer). False for unknown/expired ids."""
    with _lock:
        entry = _pending.get(ask_id)
    if entry is None:
        return False
    entry["value"] = value
    entry["event"].set()
    return True


def _normalize_options(options) -> list[dict]:
    if not isinstance(options, list):
        return []
    out: list[dict] = []
    for opt in options:
        if isinstance(opt, str):
            out.append({"label": opt})
        elif isinstance(opt, dict) and str(opt.get("label") or "").strip():
            item = {"label": str(opt["label"])}
            if opt.get("description"):
                item["description"] = str(opt["description"])
            out.append(item)
    return out


def make_ask_tool(sink: Sink) -> BoundTool:
    """Build the ask_user BoundTool bound to one turn's sink."""

    def ask(args: dict) -> str:
        question = str(args.get("question") or "").strip()
        if not question:
            return "ERROR: Missing required argument: question"
        ask_id = uuid.uuid4().hex[:6]
        entry = {"event": threading.Event(), "value": None}
        with _lock:
            _pending[ask_id] = entry
        sink.emit(
            "ask",
            {
                "id": ask_id,
                "question": question,
                "options": _normalize_options(args.get("options")),
                "allow_custom": bool(args.get("allow_custom", True)),
            },
        )
        try:
            # Heartbeat while blocked: browsers/proxies kill a fully silent
            # response stream (~300s); pings keep the NDJSON stream alive.
            deadline = time.monotonic() + ASK_TIMEOUT_S
            answered = False
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or entry["event"].wait(min(HEARTBEAT_S, remaining)):
                    answered = entry["event"].is_set()
                    break
                sink.emit("ping", None)
            if not answered:
                return "ERROR: 用户未回答"
        finally:
            with _lock:
                _pending.pop(ask_id, None)
        return f"USER: {entry['value']}"

    return BoundTool(schema=ASK_SCHEMA, fn=ask)
