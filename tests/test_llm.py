"""Tests for LLM delta assembly (offline)."""

from yesir.llm import LLMResult, _apply_delta


def test_tool_call_single_complete():
    acc: dict[int, dict] = {}
    _apply_delta(
        acc,
        {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call1",
                    "type": "function",
                    "function": {"name": "read", "arguments": '{"path"'},
                }
            ]
        },
    )
    _apply_delta(acc, {"tool_calls": [{"index": 0, "function": {"arguments": ': "a.txt"}'}}]})
    assert acc[0]["id"] == "call1"
    assert acc[0]["function"]["name"] == "read"
    assert acc[0]["function"]["arguments"] == '{"path": "a.txt"}'


def test_tool_call_parallel_indexes():
    acc: dict[int, dict] = {}
    _apply_delta(
        acc,
        {
            "tool_calls": [
                {"index": 0, "id": "a", "function": {"name": "read", "arguments": "{}"}},
                {"index": 1, "id": "b", "function": {"name": "glob", "arguments": ""}},
            ]
        },
    )
    _apply_delta(
        acc, {"tool_calls": [{"index": 1, "function": {"arguments": '{"pattern": "*.py"}'}}]}
    )
    assert acc[0]["function"]["name"] == "read"
    assert acc[1]["function"]["arguments"] == '{"pattern": "*.py"}'


def test_tool_call_missing_index_defaults_zero():
    acc: dict[int, dict] = {}
    _apply_delta(acc, {"tool_calls": [{"id": "x", "function": {"name": "bash", "arguments": ""}}]})
    assert acc[0]["function"]["name"] == "bash"


def test_delta_without_tool_calls_is_noop():
    acc: dict[int, dict] = {}
    _apply_delta(acc, {"content": "hello"})
    assert acc == {}


def test_llm_result_defaults():
    result = LLMResult()
    assert result.content == ""
    assert result.tool_calls == []
    assert result.reasoning == ""
