# Ask-User Test Set

Curated tasks to verify the planner's information-sufficiency gating: ambiguous tasks should emit `ask the user: ...` as step 1; unambiguous tasks should plan straight through without asking.

Bilingual on purpose (en + zh) — the model has shown different behaviors across languages.

Pass criteria for an **ambiguous** case:
- Planner step 1 starts with `ask the user:` (case-insensitive).
- Agent's first tool call is `ask_user`.
- Question text references the source of ambiguity (the brand, the missing parameter, the multiple matches).
- After the canned answer, the agent continues with the remaining plan rather than re-asking or calling `done`/`fail`.

Pass criteria for an **unambiguous** case:
- Planner step 1 is a concrete action (`navigate to …`, `search for …`, etc.), **not** an `ask the user:` step.
- Agent does NOT call `ask_user` at any point in the run.
- Run terminates with `done` (validator-pass not required for this test — we're checking ask-or-not, not task success).

---

## Ambiguous — should ask

### A1. Multiple branches of a brand
- **Task (zh):** `請問下禮拜六中午十二點可不可以訂位旭集？`
- **Task (en):** `Book a table at Inparadise (旭集) for noon next Saturday.`
- **Why ambiguous:** 旭集 has 6 Sogo branches (信義 / 微風 / 天母 / 中崙 / 義享 / 竹北遠百).
- **Expected question contains:** "branch", "location", "店", or lists branch names.
- **Canned answer for resume test:** `天母店 (Tianmu)`.

### A2. Common-name lookup
- **Task:** `Find the LinkedIn profile of John Smith and return his current job title.`
- **Why ambiguous:** thousands of John Smiths.
- **Expected question contains:** "which", "company", "location", or asks for a disambiguator.
- **Canned answer:** `John Smith, Director of Engineering at Stripe, based in San Francisco`.

### A3. Missing date
- **Task:** `Book a flight from Taipei to Tokyo and return the cheapest fare.`
- **Why ambiguous:** no travel date.
- **Expected question contains:** "date", "when", "depart".
- **Canned answer:** `December 15, 2026, one-way`.

### A4. Missing quantity
- **Task:** `Order coffee beans from Blue Bottle Coffee and return the order total.`
- **Why ambiguous:** no quantity, no roast, no grind preference.
- **Expected question contains:** "how many", "which", "quantity", "roast".
- **Canned answer:** `1 bag of Bella Donovan, whole bean, 12oz`.

### A5. Underspecified product variant
- **Task:** `Buy an iPhone on apple.com and return the order total.`
- **Why ambiguous:** model, storage, color, carrier all unspecified.
- **Expected question contains:** "model", "storage", "which".
- **Canned answer:** `iPhone 17 Pro, 256GB, Natural Titanium, unlocked`.

### A6. Underspecified intent (best-by-what)
- **Task:** `Find the best ramen restaurant in Tokyo on Google Maps.`
- **Why ambiguous:** "best" by rating, by reviews, by famous-list, by neighborhood?
- **Expected question contains:** "best by", "rating", "criteria", or asks for a neighborhood.
- **Canned answer:** `highest-rated by Google reviews, in Shinjuku`.

### A7. Multiple plausible meanings of an entity
- **Task (zh):** `查一下蘋果今天的股價`
- **Task (en):** `Look up today's Apple stock price.`
- **Why ambiguous:** Apple Inc. (AAPL) vs. 蘋果日報 vs. 蘋果 (the fruit).
- **Expected question contains:** "which Apple", "company", "ticker".
- **Canned answer:** `Apple Inc., NASDAQ: AAPL`.
- **Edge case note:** the model may resolve "stock price" as enough context to pick AAPL on its own. If so, accept as unambiguous and document the call.

### A8. Person + role ambiguity
- **Task:** `Find the email address of the CEO of Acme Corp.`
- **Why ambiguous:** which Acme Corp? (Many companies named Acme.)
- **Expected question contains:** "which Acme", "industry", "country".
- **Canned answer:** `Acme Corp, the cybersecurity firm headquartered in Austin, TX`.

---

## Unambiguous — should NOT ask

### U1. Specific Wikipedia page
- **Task:** `Tell me the name of the Turing Award winner in 2018.`
- **Why unambiguous:** single fact, single source. (This is webvoyager-1.)

### U2. Specific GitHub repo by full name
- **Task:** `How many open issues does the pytorch/pytorch repository have on GitHub?`
- **Why unambiguous:** fully-qualified `owner/repo`. (webvoyager-105.)

### U3. Universal fact lookup
- **Task:** `What is the current population of Tokyo according to the Wikipedia article on Tokyo?`
- **Why unambiguous:** single page, single number. (webvoyager-102.)

### U4. Specific paper by exact title
- **Task:** `Find the abstract of the paper 'Attention Is All You Need' on arXiv.`
- **Why unambiguous:** exact title in quotes. (webvoyager-2.)

### U5. Dictionary lookup
- **Task:** `What is the definition of the word 'ephemeral' according to the Cambridge Dictionary?`
- **Why unambiguous:** word in quotes, named source. (webvoyager-111.)
- **Note:** known to fail on the Cloudflare wall — that's a separate issue, not an ask_user concern.

### U6. Named-entity navigation
- **Task:** `Go to https://huggingface.co/bert-base-uncased and return the model's license.`
- **Why unambiguous:** explicit URL.

### U7. zh — specific page
- **Task (zh):** `查維基百科上「臺北 101」這個條目的完工年份。`
- **Why unambiguous:** specific Wikipedia entry, specific field.

### U8. zh — specific search target
- **Task (zh):** `在 arxiv 上找 "BERT" 這篇 2018 年論文的摘要。`
- **Why unambiguous:** specific paper, specific year, specific source.

---

## Edge cases — interesting either way

### E1. Apparently ambiguous but reasonable default
- **Task:** `What time is it in Tokyo?`
- **Acceptable:** unambiguous (assume current time). If the agent asks "current time or specific date?" that's over-asking — note as a tuning data point.

### E2. Ambiguous brand with a strong default
- **Task:** `What's the menu at Starbucks?`
- **Acceptable either way:** could pick Starbucks-global menu page; could ask for country/branch. Document which branch the model takes.

### E3. Implicit user context
- **Task:** `Find the nearest pharmacy.`
- **Should ask:** location is unknown to the agent.
- **Expected question contains:** "where", "location", "city".
- **Canned answer:** `Taipei, Da'an district`.

---

## How to use this set

1. **Manual smoke (now):** pick A1, A3, U1, U4 — fastest representative cross-section. Run each through the local agent (e.g. `/tmp/demo_ask_user.py`-style harness or the FastAPI `/sessions` endpoint once that lands). For each ambiguous case, log the actual planner step-1 text and the actual `ask_user` question text. For each unambiguous case, log the full tool-call sequence and confirm `ask_user` is absent.

2. **Soak (post-deploy):** convert this set into a YAML eval suite under `eval/cases/ask_user/` with explicit `ambiguous: bool` and `expected_question_terms: [...]` fields, and add a validator that checks the trace for the expected step-1 shape. That's a follow-up; not required for the demo.

3. **Failure modes worth noticing:**
   - **False positives** (asking on U-cases): planner is being too cautious — relax the info-sufficiency wording.
   - **False negatives** (not asking on A-cases): planner is guessing — tighten the wording.
   - **Asks the wrong question:** the question doesn't reference the actual ambiguity (e.g. asks "which date" when the date *was* given). Almost always a planner prompt issue, not a tool issue.
   - **Asks then ignores the answer:** the answer comes back but the agent re-plans without applying it. Check that the loop is feeding the answer into the next message.
