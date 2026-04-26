## ADDED Requirements

### Requirement: Configurable per-model price table

The system SHALL provide `agent.pricing` with a `load_price_table(path=None) -> dict` function that reads pricing from `task2/config/pricing.toml`. The TOML file SHALL contain a `[models.<model-id>]` section per model with `prompt_per_1k: float` and `completion_per_1k: float` keys, and a `[default]` section used as fallback for unrecognised model IDs. `load_price_table` SHALL return a plain dict of the form `{"models": {"<model-id>": {"prompt_per_1k": float, "completion_per_1k": float}}, "default": {"prompt_per_1k": float, "completion_per_1k": float}}`.

No provider rate SHALL be hardcoded in Python source. The TOML file is the only authoritative source of token prices.

#### Scenario: Loads price table from default path

- **WHEN** `load_price_table()` is called with no arguments and `task2/config/pricing.toml` exists
- **THEN** it SHALL return a dict with a `"default"` key containing `prompt_per_1k` and `completion_per_1k` floats

#### Scenario: Explicit path overrides default

- **WHEN** `load_price_table(path="/tmp/custom_pricing.toml")` is called and the file has a valid `[default]` section
- **THEN** it SHALL return the pricing from that file, not from the default path

#### Scenario: Unknown model falls back to default

- **WHEN** `compute_usd(prompt_tokens=1000, completion_tokens=500, model="unknown-model-xyz", price_table=<table>)` is called
- **THEN** it SHALL compute USD using the `[default]` rates in the price table
- **AND** it SHALL NOT raise an exception

#### Scenario: Known model uses model-specific rate

- **WHEN** `compute_usd(prompt_tokens=1000, completion_tokens=1000, model="qwen3", price_table=<table>)` is called and the table has a `[models.qwen3]` section
- **THEN** it SHALL compute USD using the `qwen3`-specific `prompt_per_1k` and `completion_per_1k` rates

### Requirement: `compute_usd` function

The system SHALL provide `agent.pricing.compute_usd(prompt_tokens: int, completion_tokens: int, model: str, price_table: dict) -> float` that computes cost as `(prompt_tokens / 1000) * prompt_per_1k + (completion_tokens / 1000) * completion_per_1k`. The price table lookup SHALL prefer `price_table["models"][model]` and fall back to `price_table["default"]`.

#### Scenario: Basic USD computation

- **WHEN** `compute_usd(prompt_tokens=2000, completion_tokens=500, model="qwen3", price_table={"models": {"qwen3": {"prompt_per_1k": 0.002, "completion_per_1k": 0.006}}, "default": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002}})` is called
- **THEN** it SHALL return `2.0 * 0.002 + 0.5 * 0.006 == 0.007`

#### Scenario: Zero tokens yields zero USD

- **WHEN** `compute_usd(prompt_tokens=0, completion_tokens=0, model="any", price_table=<valid table>)` is called
- **THEN** it SHALL return `0.0`

### Requirement: No hardcoded provider rates in Python source

The system SHALL NOT contain any float literal representing a per-token or per-1k-token price for a named LLM provider in any `.py` file under `task2/`. All rates SHALL be read from `task2/config/pricing.toml` at runtime.

#### Scenario: Grep for hardcoded rates finds nothing

- **WHEN** the test scans all `.py` files under `task2/` for patterns matching known provider rate magnitudes (e.g. `0.002`, `0.003`, `0.006` as float literals adjacent to strings like "gpt", "claude", "qwen", "llama")
- **THEN** no such literal SHALL appear outside of test fixture dicts and the TOML file itself
