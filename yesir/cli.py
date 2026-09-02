"""Console single-shot mode: `python -m yesir "question"`."""

from yesir.config import load_config
from yesir.events import ConsoleSink
from yesir.trilayer import TriLayer


def run_single_shot(query: str) -> int:
    cfg = load_config()
    if not cfg.configured:
        print("ERROR: API key not configured. Edit config.json or set OPENAI_API_KEY.")
        return 1
    sink = ConsoleSink()
    trilayer = TriLayer(cfg, sink)
    agent = trilayer.build_orchestrator(sink)
    messages = [{"role": "user", "content": query}]
    print()
    agent.run(messages)
    print()
    return 0
