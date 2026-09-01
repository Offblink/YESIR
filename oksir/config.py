"""Configuration loading: config.json first, environment variables override."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"

DEFAULT_API_KEY = "sk-your-key-here"
DEFAULT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-v4-pro"


@dataclass
class Config:
    api_key: str = DEFAULT_API_KEY
    endpoint: str = DEFAULT_ENDPOINT
    model: str = DEFAULT_MODEL
    system_prompt: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and self.api_key != DEFAULT_API_KEY


def load_config(path: Path | None = None) -> Config:
    """Load config from JSON file, then apply env overrides."""
    cfg = Config()
    source = path if path is not None else CONFIG_PATH
    if source.is_file():
        try:
            data = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if data.get("api_key"):
            cfg.api_key = data["api_key"]
        if data.get("endpoint"):
            cfg.endpoint = data["endpoint"]
        if data.get("model"):
            cfg.model = data["model"]
        if data.get("system_prompt"):
            cfg.system_prompt = data["system_prompt"]
    cfg.api_key = os.environ.get("OPENAI_API_KEY") or cfg.api_key
    cfg.endpoint = os.environ.get("OPENAI_ENDPOINT") or cfg.endpoint
    cfg.model = os.environ.get("OPENAI_MODEL") or cfg.model
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    """Persist api_key/endpoint/model (and system_prompt when set) to JSON."""
    target = path if path is not None else CONFIG_PATH
    data: dict[str, str] = {
        "api_key": cfg.api_key,
        "endpoint": cfg.endpoint,
        "model": cfg.model,
    }
    if cfg.system_prompt:
        data["system_prompt"] = cfg.system_prompt
    target.write_text(json.dumps(data, indent=4), encoding="utf-8")
