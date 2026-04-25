import os

import pytest


@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch):
    for var in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    yield
