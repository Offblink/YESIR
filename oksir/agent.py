"""Agent turn loop: stream a completion, dispatch tool calls, repeat (max rounds)."""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass

from oksir import tools
from oksir.config import Config
from oksir.events import Sink
from oksir.llm import LLMError, LLMResult, stream_chat

MAX_TOOL_ROUNDS = 25
TRUNCATE_TOOL_RESULT = 8000

SYSTEM_PROMPT = """\
You are a coding assistant. You have tools to read, write, edit files, run
shell commands, search code, and access the web. Core rules:

- Be concise. Lead with the answer, then evidence.
- NEVER ask for permission — just do the work.
- BEFORE any task: use `glob` to see directory structure. NEVER `bash dir` or `bash ls`.
- To find files or code: use `grep`. NEVER `bash find` or `bash findstr`.
- To read a file: use `read`. NEVER `bash type` or `bash cat`.
- To edit: use `edit`. NEVER `bash echo >` to overwrite files.
- `bash` is ONLY for: running programs, builds, tests, git, pip, npm, python, etc.
- When editing, match the existing code style. Use the edit tool (old_string /
  new_string) for surgical changes, not rewrite the whole file.
- When you need up-to-date information, use `web_search` to find sources,
  then `web` to read the full pages you need.

- Tool output is truncated at ~8000 chars. Plan reads accordingly.
- After completing a task, summarize what you did.
- NEVER fabricate file contents or command output.
- If a tool returns no results or an error, try a different approach —
  don't just give up.

- When answering in the browser, use full markdown: code blocks, lists, bold, etc.
"""


@dataclass
class BoundTool:
    """An agent-bound tool beyond the base registry (spawn, ask_user, ...)."""

    schema: dict
    fn: Callable[..., str]
    with_call_id: bool = False  # fn also receives the tool_call id


class Agent:
    """One agent conversation loop. Owns no history: the caller passes the message list.

    `extra_tools` (BoundTool by name) lets upper layers attach dispatch/ask
    tools (see oksir.trilayer / oksir.tools.ask). `llm` is injectable so tests
    can drive the loop with scripted completions.
    """

    def __init__(
        self,
        cfg: Config,
        sink: Sink,
        system_prompt: str = SYSTEM_PROMPT,
        tool_names: frozenset[str] | set[str] | None = None,
        extra_tools: dict[str, BoundTool] | None = None,
        llm: Callable[[list[dict], list[dict]], LLMResult] | None = None,
        parallel_tools: frozenset[str] | set[str] = frozenset(),
    ) -> None:
        self.cfg = cfg
        self.sink = sink
        self.system_prompt = system_prompt
        self.tool_names = tool_names
        self.extra_tools = extra_tools or {}
        self.parallel_tools = frozenset(parallel_tools)
        self._llm = llm

    @property
    def tool_defs(self) -> list[dict]:
        defs = tools.tool_defs(self.tool_names)
        defs.extend(bound.schema for bound in self.extra_tools.values())
        return defs

    def _default_llm(self, messages: list[dict], tool_defs: list[dict]) -> LLMResult:
        def on_delta(kind: str, text: str) -> None:
            self.sink.emit(kind, text)

        return stream_chat(
            self.cfg.model, self.cfg.endpoint, self.cfg.api_key, messages, tool_defs, on_delta
        )

    def _dispatch(self, name: str, args: dict, call_id: str | None = None) -> str:
        bound = self.extra_tools.get(name)
        if bound is not None:
            try:
                if bound.with_call_id:
                    return str(bound.fn(args, call_id))
                return str(bound.fn(args))
            except Exception as exc:
                return f"ERROR: {exc}"
        return tools.dispatch(name, args)

    def _run_tool_call(self, tc: dict, messages: list[dict]) -> None:
        name = tc["function"]["name"]
        raw_args = tc["function"]["arguments"]
        try:
            args = json.loads(raw_args or "{}")
        except json.JSONDecodeError:
            args = {}
        self.sink.emit("tool", {"name": name, "args": raw_args, "id": tc["id"]})
        output = self._dispatch(name, args, call_id=tc["id"])
        self.sink.emit("tool_result", {"content": _truncate(output), "id": tc["id"]})
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})

    def run(self, messages: list[dict]) -> LLMResult:
        """Drive one user turn to completion, mutating `messages` in place."""
        if not any(m.get("role") == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": self.system_prompt})

        result = LLMResult()
        for _round in range(MAX_TOOL_ROUNDS):
            llm = self._llm if self._llm is not None else self._default_llm
            try:
                result = llm(messages, self.tool_defs)
            except LLMError as exc:
                self.sink.emit("error", str(exc))
                messages.append({"role": "assistant", "content": f"(LLM error: {exc})"})
                return result

            if not result.tool_calls:
                messages.append(
                    {"role": "assistant", "content": result.content, "reasoning": result.reasoning}
                )
                return result

            messages.append(
                {
                    "role": "assistant",
                    "content": result.content or None,
                    "tool_calls": result.tool_calls,
                    "reasoning": result.reasoning,
                }
            )
            self._run_tool_calls(result.tool_calls, messages)

        self.sink.emit("error", f"Max tool rounds ({MAX_TOOL_ROUNDS}) reached")
        hit = f"(Hit max tool rounds: {MAX_TOOL_ROUNDS}.)"
        messages.append({"role": "assistant", "content": hit})
        return result

    def _run_tool_calls(self, tool_calls: list[dict], messages: list[dict]) -> None:
        """Dispatch tool calls; run them concurrently when all are whitelisted as parallel."""
        parallel = len(tool_calls) > 1 and all(
            tc["function"]["name"] in self.parallel_tools for tc in tool_calls
        )
        if not parallel:
            for tc in tool_calls:
                self._run_tool_call(tc, messages)
            return

        parsed = [(tc, self._parse_args(tc)) for tc in tool_calls]
        for tc, _args in parsed:
            self.sink.emit(
                "tool",
                {
                    "name": tc["function"]["name"],
                    "args": tc["function"]["arguments"],
                    "id": tc["id"],
                },
            )
        outputs: list[str] = [""] * len(parsed)

        def worker(index: int, tc: dict, args: dict) -> None:
            outputs[index] = self._dispatch(tc["function"]["name"], args, call_id=tc["id"])

        threads = [
            threading.Thread(target=worker, args=(i, tc, args), daemon=True)
            for i, (tc, args) in enumerate(parsed)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for (tc, _args), output in zip(parsed, outputs, strict=True):
            self.sink.emit("tool_result", {"content": _truncate(output), "id": tc["id"]})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})

    @staticmethod
    def _parse_args(tc: dict) -> dict:
        try:
            return json.loads(tc["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return {}


def _truncate(text: str, limit: int = TRUNCATE_TOOL_RESULT) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n... [truncated {len(text) - limit} chars] ...\n{text[-half:]}"
