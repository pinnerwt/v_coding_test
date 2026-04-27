# /new_task2 — simplify pattern catalog

Read this at Step 8 of `/new_task2` once the diff for `<change-name>` is in context. Each entry is a recurring shape this loop has produced; check the diff against every one and apply the listed collapse only where the existing tests still pass after.

This file is append-mostly — when a new pattern shows up across two or more tickets, add it here rather than re-deriving it next run.

---

- **Dead fallback branches.** When the ticket adds a new attribute to a class (`self._cdp_sessions`, `self._foo`) and you've already updated test fixtures / `SimpleNamespace` doubles to set it, any `getattr(obj, attr, None)` "fallback" branch is dead code. Drop the branch entirely; assume the attribute is present. Keep it only if a real, non-test caller exists.

- **Per-test boilerplate.** Three new tests building the same `data:text/html;base64,...` URL inline → hoist to a module-level constant (`_BUTTON_DATA_URL`) or fixture. Ditto duplicated `import base64 as _b64` shadowing a module-level `import base64`.

- **Branch-duplicated `try/finally`.** If two if/else branches both end in the same `cdp.send(...)` + `try: cdp.detach() except: pass` pattern, consolidate to one send + one finally below the if/else and gate the detach on a `transient` flag. (Then per the dead-branch rule above, often one branch can be removed entirely.)

- **Branch-duplicated `dict` builds.** Two if/else branches both build a dict that shares 3-of-4 keys (e.g. `last_actions.append({"tool": ..., "intent": ..., "outcome": "ok"})` vs. `... "outcome": "error", "error": tool_result`). Collapse to one dict literal with a ternary on the differing key, then conditionally `dict[extra_key] = value` for the error-only field. Reuse the boolean (`is_error = ...`) for any later branch that re-checks the same condition (e.g. supervisor halt detection two lines down).

- **Per-test scripted-LLM client classes.** When two new `loop.py` tests each define a near-identical `_FooClient` with `chat(messages, *, tools=...)` returning a different first-step `ChatResponse` and the same final `done` response, parameterize one shared `_ScriptedFirstStepClient(first_step_calls, done_evidence_url)` instead. The pattern is "first call returns scripted tool calls, second call returns `done`" — only the `tool_calls` list and the evidence URL vary.

- **Repeated observation-from-captures extraction.** The pattern `obs_msg = next(m for m in reversed(captures[N]) if m["role"] == "user" and "Current state:" in m.get("content", "")); obs = _extract_obs_json(obs_msg["content"])` repeats across multi-step loop tests. Hoist a `_step_observation(captures, step_index) -> dict` helper next to `_extract_obs_json`. Apply it to existing migrated assertions too (e.g. `test_second_step_last_action_populated`), not just the new tests, to keep the file consistent.
