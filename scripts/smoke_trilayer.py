"""End-to-end smoke test: real LLM through the full L1 -> L2 -> L3 chain.

Run:  python smoke_trilayer.py   (uses config.json credentials)
"""

import sys
import time

from yesir.config import load_config
from yesir.events import FnSink
from yesir.trilayer import TriLayer

cfg = load_config()
if not cfg.configured:
    sys.exit("config.json has no real api_key - aborting smoke test")

print(f"model={cfg.model} endpoint={cfg.endpoint}")

events: list[tuple[str, object]] = []
sink = FnSink(lambda t, c: events.append((t, c)))

tl = TriLayer(cfg, sink)
orchestrator = tl.build_orchestrator(sink)

USER = """Smoke test of the TriLayer dispatch mechanism. Follow this choreography EXACTLY:

1. Use the spawn tool to dispatch ONE L2 Task Agent.
   - goal: "Spawn one L3 Worker. The L3 worker must run exactly one bash command:
     python -c \\"print(6*7)\\" and report its exact stdout. Then reply with JSON."
   - reply_format: 'JSON {"worker_said": "<exact stdout string>"}'
2. When the L2 reply comes back, finish.

Do not use any other tool yourself. Keep everything minimal."""

t0 = time.time()
result = orchestrator.run([{"role": "user", "content": USER}])
elapsed = time.time() - t0

print(f"\n=== elapsed: {elapsed:.1f}s ===")
print(f"\n=== L1 final reply ===\n{result.content}")

print("\n=== spawn/status events ===")
for t, c in events:
    if t in ("agent_spawn", "agent_status"):
        goal = c.get("goal", c.get("status", ""))
        print(f"[{t}] layer={c.get('layer', '-')!s:<3} id={c.get('id')} {str(goal)[:80]}")

print("\n=== subagent records ===")
for sid, rec in tl.subagents.items():
    kinds = [e["type"] for e in rec["events"]]
    print(
        f"id={sid} layer={rec['layer']} status={rec['status']} "
        f"call_id={rec['call_id']} events={kinds}"
    )
    for e in rec["events"]:
        if e["type"] == "tool":
            print(f"    tool: {e['content']}")
        if e["type"] == "assistant" and isinstance(e["content"], str):
            print(f"    final: {e['content'][:120]}")

spawned = [c for t, c in events if t == "agent_spawn"]
statuses = {c["status"] for t, c in events if t == "agent_status"}
ok = (
    len(spawned) >= 2
    and any(s["layer"] == 2 for s in spawned)
    and any(s["layer"] == 3 for s in spawned)
    and "done" in statuses
    and "failed" not in statuses
    and all(r["status"] == "done" for r in tl.subagents.values())
)
print(f"\n=== SMOKE TEST {'PASSED' if ok else 'FAILED'} ===")
sys.exit(0 if ok else 1)
