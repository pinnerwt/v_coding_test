from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import agent.llm as llm_mod


def test_default_llm_model_constant_value():
    assert llm_mod._DEFAULT_LLM_MODEL == "qwen3-5-27b"


def test_build_clients_uses_shared_default_when_env_unset():
    from scripts.eval import build_clients

    env = {k: v for k, v in os.environ.items() if k != "LLM_MODEL"}
    with (
        patch.dict(os.environ, env, clear=True),
        patch("scripts.eval.LLMClient") as mock_llm,
        patch("scripts.eval.Browser") as mock_browser,
    ):
        mock_llm.return_value = MagicMock()
        mock_browser.return_value = MagicMock()
        build_clients()
        _, kwargs = mock_llm.call_args
        assert kwargs.get("model") == llm_mod._DEFAULT_LLM_MODEL


def test_server_default_matches_shared_constant():
    env = {k: v for k, v in os.environ.items() if k != "LLM_MODEL"}
    with patch.dict(os.environ, env, clear=True):
        resolved = os.environ.get("LLM_MODEL", llm_mod._DEFAULT_LLM_MODEL)
        assert resolved == "qwen3-5-27b"
        assert resolved == llm_mod._DEFAULT_LLM_MODEL


def test_qwen3_literal_absent_from_eval_py():
    import scripts.eval as eval_mod

    eval_py = Path(eval_mod.__file__).resolve()
    source = eval_py.read_text()
    assert '"qwen3"' not in source


def test_api_server_imports_shared_default_constant():
    import api.server as server_mod

    assert server_mod._DEFAULT_LLM_MODEL is llm_mod._DEFAULT_LLM_MODEL
