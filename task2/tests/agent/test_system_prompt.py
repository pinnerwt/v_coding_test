from __future__ import annotations

from agent.loop import _VERIFY_DONE_SYSTEM_PROMPT, _build_system_prompt
from agent.plan import _PLAN_SYSTEM


def test_system_prompt_contains_only_for_irrecoverable():
    prompt = _build_system_prompt("dummy task")
    assert "only for irrecoverable conditions" in prompt


def test_system_prompt_contains_action_first_guidance():
    prompt = _build_system_prompt("dummy task")
    assert "attempt `click`/`type`" in prompt


def test_system_prompt_does_not_contain_old_phrasing():
    prompt = _build_system_prompt("dummy task")
    assert "If you cannot complete the task, call" not in prompt


def test_system_prompt_names_irrecoverable_conditions():
    prompt = _build_system_prompt("dummy task")
    assert "login walls" in prompt
    assert "captchas" in prompt
    assert "pages that don't exist" in prompt
    assert "genuinely absent from the page" in prompt


_SCHEMA_MARKER = "MUST be a JSON object matching this schema"


def test_build_system_prompt_schema_present():
    prompt = _build_system_prompt(
        "find the price",
        expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]},
    )
    assert _SCHEMA_MARKER in prompt
    assert "answer" in prompt


def test_build_system_prompt_schema_absent():
    prompt = _build_system_prompt("find the price")
    assert "browser automation agent" in prompt
    assert "find the price" in prompt
    assert "only for irrecoverable conditions" in prompt
    assert _SCHEMA_MARKER not in prompt
    assert _build_system_prompt("find the price") == _build_system_prompt(
        "find the price", expect=None
    )


def test_build_system_prompt_empty_schema_leaves_no_schema_clause():
    prompt = _build_system_prompt(
        "find the price",
        expect={"schema": {}, "validators": []},
    )
    assert _SCHEMA_MARKER not in prompt
    assert prompt == _build_system_prompt("find the price")


def test_build_system_prompt_required_keys_appear_sorted():
    prompt = _build_system_prompt(
        "task",
        expect={"schema": {"title": "str", "answer": "str"}, "validators": []},
    )
    assert "answer, title" in prompt
    assert "title, answer" not in prompt


# --- de-anchoring: planner examples must not name eval-case entities --------

# Phrases below are concrete entities lifted from the eval set
# (ask_user_test_set.md cases A1/A3/A6/U1). Their presence in
# `_PLAN_SYSTEM` constitutes bench-maxxing — a real user task that
# doesn't share these shapes loses guidance the eval cases get for free.
_PLAN_FORBIDDEN_PHRASES = (
    "Tokyo",
    "Taipei",
    "Turing Award",
    "Google Maps",
    "ramen",
    "Tianmu",
    "Inparadise",
    "2018",
    "2026-12-15",
    "flight",
    "airline",
)


def test_plan_system_has_no_eval_case_entities():
    haystack = _PLAN_SYSTEM.lower()
    for phrase in _PLAN_FORBIDDEN_PHRASES:
        assert phrase.lower() not in haystack, (
            f"_PLAN_SYSTEM names eval-case entity {phrase!r}; "
            f"examples must be shape-only, not domain-specific"
        )


# The verify-done prompt's named-entity examples must stay neutral. "airlines"
# is the category shape of the flight-booking eval case (Taipei→Tokyo) — a
# generic verifier should list entity *kinds*, not domain instances.
_VERIFY_DONE_FORBIDDEN_DOMAIN_TERMS = (
    "airline",
    "flight",
    "hotel",
    "restaurant",
)


def test_verify_done_system_drops_domain_examples():
    s = _VERIFY_DONE_SYSTEM_PROMPT.lower()
    for term in _VERIFY_DONE_FORBIDDEN_DOMAIN_TERMS:
        assert term not in s, (
            f"_VERIFY_DONE_SYSTEM_PROMPT lists domain-specific entity {term!r}; "
            f"named-entity examples must be neutral (prices, dates, addresses, "
            f"proper names)"
        )


def test_plan_system_keeps_shape_only_taxonomy():
    s = _PLAN_SYSTEM.lower()
    # The three shape categories must remain documented for the planner.
    assert "ambiguous" in s
    assert "comparator" in s
    assert "fact" in s or "lookup" in s


# --- soften the early-`done` bias -------------------------------------------

# Bench-shaped urgency framings; their absence is the win condition for
# fix item (2). Real-user tasks are not 20-step-budgeted, so manufactured
# urgency around step 12 / "the MOMENT" optimises for the benchmark, not
# correctness.
_LOOP_FORBIDDEN_URGENCY_PHRASES = (
    "MOMENT you can plausibly",
    "by step 12",
    "Bias strongly toward calling",
)


def test_loop_system_drops_urgency_framing():
    prompt = _build_system_prompt("dummy task")
    for phrase in _LOOP_FORBIDDEN_URGENCY_PHRASES:
        assert phrase not in prompt, (
            f"loop system prompt still contains urgency phrase {phrase!r} — "
            f"violates fix (2): bias should be 'grounded then done', not 'done early'"
        )


def test_loop_system_keeps_grounded_done_rule():
    prompt = _build_system_prompt("dummy task")
    # The replacement language: only call done once the answer is grounded.
    assert "grounded in" in prompt
    assert "20 steps" in prompt  # hard ceiling preserved


# --- drop the listing/aggregator site-shape heuristic -----------------------

# These phrases are site-shape advice; per the no-preseeding-domains rule
# the prompt must speak in page-shape generalities, not site categories.
_LOOP_FORBIDDEN_SITE_SHAPE_PHRASES = (
    "Listing/aggregator",
    "brand's official site",
)


def test_loop_system_drops_site_shape_heuristics():
    prompt = _build_system_prompt("dummy task")
    for phrase in _LOOP_FORBIDDEN_SITE_SHAPE_PHRASES:
        assert phrase not in prompt, (
            f"loop system prompt still names site shape {phrase!r}; "
            f"agent must be generalised — phrase as page-shape rule instead"
        )


def test_loop_system_uses_page_shape_no_progress_rule():
    prompt = _build_system_prompt("dummy task")
    # The generalised replacement: condition on observed page state, not
    # on what *kind* of site you are on.
    assert "no URL change" in prompt
    assert "no new content" in prompt
