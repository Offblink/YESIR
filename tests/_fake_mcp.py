"""Minimal MCP stdio server (legacy era) for tests and E2E.

Tools: echo(text), add(a, b), slow(seconds) — sleeps for the timeout path,
fail() — returns an isError result. Speaks the 2025-06-18 handshake.
"""

import json
import sys
import time

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the given text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "Add two integers.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "slow",
        "description": "Sleep for the given seconds, then reply.",
        "inputSchema": {
            "type": "object",
            "properties": {"seconds": {"type": "number"}},
            "required": ["seconds"],
        },
    },
    {
        "name": "fail",
        "description": "Always reports a tool error.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def reply(rid, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}) + "\n")
    sys.stdout.flush()


def call(name, args):
    if name == "echo":
        return f"echo: {args.get('text', '')}", False
    if name == "add":
        return str(int(args.get("a", 0)) + int(args.get("b", 0))), False
    if name == "slow":
        time.sleep(float(args.get("seconds", 0)))
        return "finally awake", False
    if name == "fail":
        return "the demo tool failed on purpose", True
    return f"unknown tool: {name}", True


def main():
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = msg.get("method"), msg.get("id")
        if method == "initialize":
            reply(
                rid,
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp", "version": "0.0.0"},
                },
            )
        elif method == "tools/list":
            reply(rid, {"tools": TOOLS})
        elif method == "tools/call":
            params = msg.get("params") or {}
            text, is_error = call(str(params.get("name")), params.get("arguments") or {})
            reply(rid, {"content": [{"type": "text", "text": text}], "isError": is_error})
        elif rid is not None:
            reply(rid, {})


if __name__ == "__main__":
    main()
