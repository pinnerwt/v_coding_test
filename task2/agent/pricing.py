from __future__ import annotations

import tomllib
from pathlib import Path

_DEFAULT_TOML_PATH = Path(__file__).parent.parent / "config" / "pricing.toml"


def load_price_table(path: str | None = None) -> dict:
    resolved = Path(path) if path is not None else _DEFAULT_TOML_PATH
    with resolved.open("rb") as f:
        raw = tomllib.load(f)
    default = raw.get("default", {"prompt_per_1k": 0.0, "completion_per_1k": 0.0})
    models = raw.get("models", {})
    return {"models": models, "default": default}


def compute_usd(
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    price_table: dict,
) -> float:
    rates = price_table.get("models", {}).get(model) or price_table.get("default", {})
    prompt_rate = rates.get("prompt_per_1k", 0.0)
    completion_rate = rates.get("completion_per_1k", 0.0)
    return (prompt_tokens / 1000) * prompt_rate + (completion_tokens / 1000) * completion_rate
