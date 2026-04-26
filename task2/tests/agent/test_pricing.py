from __future__ import annotations

import re
from pathlib import Path

from agent.pricing import compute_usd, load_price_table

_SYNTHETIC_TABLE = {
    "models": {
        "qwen3": {"prompt_per_1k": 0.002, "completion_per_1k": 0.006},
    },
    "default": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002},
}

_FIXTURE_TOML = """\
[default]
prompt_per_1k = 0.001
completion_per_1k = 0.002

[models.qwen3]
prompt_per_1k = 0.002
completion_per_1k = 0.006
"""


def test_compute_usd_known_model():
    result = compute_usd(
        prompt_tokens=2000,
        completion_tokens=500,
        model="qwen3",
        price_table=_SYNTHETIC_TABLE,
    )
    assert abs(result - 0.007) < 1e-9


def test_compute_usd_unknown_model_falls_back_to_default():
    result = compute_usd(
        prompt_tokens=1000,
        completion_tokens=1000,
        model="unknown-model-xyz",
        price_table=_SYNTHETIC_TABLE,
    )
    assert abs(result - (1.0 * 0.001 + 1.0 * 0.002)) < 1e-9


def test_compute_usd_unknown_model_does_not_raise():
    result = compute_usd(
        prompt_tokens=1000,
        completion_tokens=500,
        model="unknown-model-xyz",
        price_table=_SYNTHETIC_TABLE,
    )
    assert isinstance(result, float)


def test_compute_usd_zero_tokens():
    result = compute_usd(
        prompt_tokens=0,
        completion_tokens=0,
        model="qwen3",
        price_table=_SYNTHETIC_TABLE,
    )
    assert result == 0.0


def test_load_price_table_from_explicit_path(tmp_path):
    toml_file = tmp_path / "pricing.toml"
    toml_file.write_text(_FIXTURE_TOML)
    table = load_price_table(path=str(toml_file))
    assert "default" in table
    assert "prompt_per_1k" in table["default"]
    assert "completion_per_1k" in table["default"]
    assert "models" in table
    assert "qwen3" in table["models"]


def test_load_price_table_from_default_path():
    table = load_price_table()
    assert "default" in table
    assert "prompt_per_1k" in table["default"]
    assert "completion_per_1k" in table["default"]


def test_load_price_table_explicit_path_does_not_use_default(tmp_path):
    custom_toml = tmp_path / "custom.toml"
    custom_toml.write_text("[default]\nprompt_per_1k = 9.99\ncompletion_per_1k = 9.99\n")
    table = load_price_table(path=str(custom_toml))
    assert abs(table["default"]["prompt_per_1k"] - 9.99) < 1e-6


_PROVIDER_RATE_PATTERN = re.compile(
    r"\b0\.00[0-9]\b|\b0\.0[0-9]{2}\b",
)
_PROVIDER_CONTEXT_PATTERN = re.compile(
    r"(gpt|claude|qwen|llama|mistral|gemini)",
    re.IGNORECASE,
)

_TASK2_ROOT = Path(__file__).parent.parent.parent


def test_no_hardcoded_provider_rates_in_python_source():
    """No float literal representing a per-token price for a named provider in .py source."""
    violations: list[str] = []
    for py_file in _TASK2_ROOT.rglob("*.py"):
        if "tests" in py_file.parts:
            continue
        source = py_file.read_text()
        for lineno, line in enumerate(source.splitlines(), 1):
            if _PROVIDER_RATE_PATTERN.search(line) and _PROVIDER_CONTEXT_PATTERN.search(line):
                violations.append(f"{py_file}:{lineno}: {line.strip()}")
    assert violations == [], "Hardcoded provider rate floats found:\n" + "\n".join(violations)
