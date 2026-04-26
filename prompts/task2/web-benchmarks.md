# Web Agent Benchmark Research Brief

## Overview

This brief surveys seven publicly available benchmarks for evaluating web-browsing agents. For each benchmark, the license, scope, hosting cost, task format, and headline metric are documented. A recommendation section names the selected benchmark for integration.

---

## WebArena

**License:** MIT

**Scope:** Live web (Docker-hosted snapshots of real sites — Reddit, shopping, GitLab, etc.)

**Hosting cost:** High — each task requires running multiple Docker containers (one per site). Estimated 4–8 GB RAM per benchmark run.

**Task format:** JSON task descriptors with fields `sites` (list of site IDs), `intent` (instruction), `eval` (evaluation script reference), and `config_file` (task configuration). Requires a running WebArena server cluster.

**Headline metric:** Task success rate (%) evaluated by site-specific functional oracles (DOM inspection, API response checks).

**Integration verdict:** Rejected — requires self-hosted Docker infrastructure per task; not feasible without dedicated server capacity.

---

## Mind2Web

**License:** MIT

**Scope:** Snapshot / DOM replay (offline traces of recorded browser sessions from 137 real websites)

**Hosting cost:** None — dataset is on Hugging Face; no live browser needed for offline evaluation.

**Task format:** JSON records with fields `annotation_id`, `website`, `domain`, `subdomain`, `confirmed_task` (instruction), `action_reprs` (list of recorded actions), and `snapshot_url`.

**Headline metric:** Element accuracy (correct DOM element selected), operation F1, and step success rate averaged across tasks.

**Online-Mind2Web variant:** Live-web extension of Mind2Web with real URLs and an online evaluation protocol; requires Hugging Face dataset API access and a live browser.

**Integration verdict:** Rejected — offline variant replays frozen DOM snapshots and cannot exercise our live browser loop; online variant requires HF dataset download tooling.

---

## BrowserGym

**License:** Apache-2.0

**Scope:** Simulated + live web (Gym-compatible environment wrapping both MiniWoB++ tasks and live-web tasks via WorkArena and AssistantBench)

**Hosting cost:** Medium — WorkArena task set requires a ServiceNow developer instance; base MiniWoB++ tasks are local HTML.

**Task format:** Gym step API — tasks are specified via `task_kwargs` dicts and accessed through `env.reset()` / `env.step()`. Does not expose plain JSON task lists.

**Headline metric:** Task completion rate on the enabled task set (MiniWoB++, WorkArena, or AssistantBench).

**Integration verdict:** Rejected — Gym API does not map cleanly to our `loop()` signature without a non-trivial adapter; WorkArena requires cloud infra.

---

## WebVoyager

**License:** CC BY 4.0

**Scope:** Live web (real websites — Wikipedia, Booking, GitHub, Google, arXiv, Cambridge, etc.)

**Hosting cost:** None — the full task list is a single JSON file; no server required.

**Task format:** JSON list of objects with fields `id`, `web_name` (site label), `ques` (task instruction), `web` (start URL, `https://`).

**Headline metric:** Task completion rate (%) as judged by GPT-4V human-in-the-loop evaluation on 643 tasks across 15 websites.

**Integration verdict:** **SELECTED** — see Recommendation section below.

---

## MiniWoB++

**License:** MIT

**Scope:** Simulated (mini HTML task environments served locally — forms, calendars, dialogs)

**Hosting cost:** Low — requires running a local Python HTTP server for the HTML task files.

**Task format:** Python gym-compatible API; tasks identified by string IDs (e.g., `miniwob/click-button`). No standalone JSON task list.

**Headline metric:** Mean task success rate (%) across 100+ task types; human baseline is ~95%.

**Integration verdict:** Rejected — simulated HTML environments do not exercise real-web generalization; requires local server.

---

## WebShop

**License:** MIT

**Scope:** Simulated (shopping environment with ~1.18M real Amazon products, served via a local Flask app)

**Hosting cost:** Medium — requires running the WebShop server (Flask + ElasticSearch); dataset is ~10 GB.

**Task format:** Structured shopping queries generated from product metadata: `instruction_text` (e.g., "I need a blue backpack under $50"), `attribute_filters`, and `goal_item` for evaluation.

**Headline metric:** Task success rate (exact product match) and score (attribute overlap).

**Integration verdict:** Rejected — requires a running WebShop server and large dataset; scope is shopping-only (narrow domain).

---

## GAIA (Web Subset)

**License:** CC BY 4.0

**Scope:** Live web (general AI assistant tasks requiring web browsing, tool use, and multi-step reasoning)

**Hosting cost:** None — dataset is on Hugging Face; test set answers are held out, validation set is public.

**Task format:** JSON records with fields `task_id`, `Question`, `Level` (1–3 difficulty), `Final answer`, `Annotator Metadata` (steps, tools, file names). Validation set has 165 tasks.

**Headline metric:** Task accuracy (%) — exact answer match against gold final answer.

**Integration verdict:** Viable but not selected — GAIA tasks are general question-answering with web search, not pure browser automation tasks; less aligned with our tool surface than WebVoyager.

---

## Recommendation: WebVoyager (Selected)

**Selected benchmark: WebVoyager**

WebVoyager is the best fit for integration with our browser automation agent for the following reasons:

1. **License (CC BY 4.0):** Permissive license allows research use with attribution. No viral or commercial restrictions.

2. **Hosting cost (none):** The complete task list is a single JSON file downloadable from the public GitHub repository. No Docker containers, no cloud infra, no local servers required. Benchmark cases run against live public websites.

3. **Task format simplicity:** Each task entry has exactly four fields — `id`, `web_name`, `ques`, `web` — which map directly to our `Case` schema:
   - `ques` → `task` (instruction for the agent)
   - `web` → `domain` (start URL for `goto`)
   - `web_name` → `category` (site label)
   - `id` → `id` (prefixed `webvoyager-`)

4. **Fit with our Case schema:** The field mapping is one-to-one with no impedance mismatch. `expect` and `budget` are set to fixed defaults (`answer.nonempty` validator; 20-step / $0.25 / 120s budget). No adapter layer needed.

5. **Live-web scope:** WebVoyager tasks exercise real websites, matching our agent's intended operating environment. Tasks span 15 sites (Wikipedia, arXiv, GitHub, Booking, Cambridge Dictionary, etc.) covering diverse navigation patterns.

**Attribution:** Dataset and tasks from the WebVoyager paper (He et al., 2024): "WebVoyager: Building an End-to-End Web Agent with Large Multimodal Models." Licensed under CC BY 4.0. Source: https://github.com/MinorJerry/WebVoyager
