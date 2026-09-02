"""MCP client tests against a real stdio subprocess (tests/_fake_mcp.py)."""

import sys
from pathlib import Path

import pytest

from yesir.config import Config, load_config, save_config
from yesir.tools.mcp import (
    McpError,
    McpServer,
    McpTimeoutError,
    mcp_extra_tools,
    shutdown_servers,
    tool_name,
)

FAKE = str(Path(__file__).parent / "_fake_mcp.py")
SPEC = {"command": sys.executable, "args": [FAKE]}


@pytest.fixture(name="server")
def fixture_server():
    server = McpServer("demo", SPEC)
    yield server
    server.close()


def test_handshake_and_list_tools(server: McpServer) -> None:
    tools = server.list_tools()
    names = {t["name"] for t in tools}
    assert names == {"echo", "add", "slow", "fail"}
    echo = next(t for t in tools if t["name"] == "echo")
    assert echo["inputSchema"]["required"] == ["text"]


def test_call_tool_echo_and_add(server: McpServer) -> None:
    assert server.call_tool("echo", {"text": "hello"}) == "echo: hello"
    assert server.call_tool("add", {"a": 2, "b": 40}) == "42"


def test_call_tool_is_error_is_prefixed(server: McpServer) -> None:
    out = server.call_tool("fail", {})
    assert out.startswith("ERROR:")
    assert "on purpose" in out


def test_call_tool_timeout_sends_cancellation(server: McpServer) -> None:
    with pytest.raises(McpTimeoutError):
        server.call_tool("slow", {"seconds": 2}, timeout=0.5)
    # The server must still be usable after the cancelled request.
    assert server.call_tool("echo", {"text": "alive"}) == "echo: alive"


def test_reconnect_after_process_death(server: McpServer) -> None:
    server.list_tools()
    assert server._conn is not None
    server._conn.proc.kill()
    server._conn.proc.wait(timeout=5)
    assert server.list_tools()  # fresh handshake on next use


def test_missing_command_raises() -> None:
    server = McpServer("broken", {"command": ""})
    with pytest.raises(McpError):
        server.list_tools()


def test_tool_name_sanitization() -> None:
    assert tool_name("my.server", "do thing") == "mcp__my_server__do_thing"


def test_mcp_extra_tools_builds_bound_tools() -> None:
    tools = mcp_extra_tools({"demo.server": SPEC})
    try:
        assert "mcp__demo_server__echo" in tools
        bound = tools["mcp__demo_server__echo"]
        assert bound.schema["type"] == "function"
        fn = bound.schema["function"]
        assert fn["name"] == "mcp__demo_server__echo"
        assert "MCP server: demo.server" in fn["description"]
        assert fn["parameters"]["required"] == ["text"]
        assert bound.fn({"text": "ping"}) == "echo: ping"
    finally:
        shutdown_servers()


def test_mcp_extra_tools_skips_broken_server(capsys: pytest.CaptureFixture[str]) -> None:
    tools = mcp_extra_tools({"nope": {"command": "definitely-missing-binary-xyz"}, "demo": SPEC})
    try:
        assert "mcp__demo__add" in tools
        err = capsys.readouterr().err
        assert "[mcp] server 'nope' unavailable" in err
    finally:
        shutdown_servers()


def test_mcp_extra_tools_empty_when_unconfigured() -> None:
    assert mcp_extra_tools({}) == {}


def test_config_round_trip_preserves_mcp_servers(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cfg = Config(api_key="k", mcp_servers={"demo": SPEC})
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.mcp_servers == {"demo": SPEC}
    # Non-dict mcp_servers entries are dropped, not crash.
    path.write_text('{"mcp_servers": ["bad"], "api_key": "k"}', encoding="utf-8")
    assert load_config(path).mcp_servers == {}
