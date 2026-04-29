## Context

{{context_paragraph}}

The relevant symbols:
- `{{symbol_1}}` in `{{file_path_1}}` — {{symbol_1_role}}.
- `{{symbol_2}}` in `{{file_path_2}}` — {{symbol_2_role}}.
- {{existing_invariant}}.

## Goals / Non-Goals

**Goals:**

- {{goal_1}}.
- {{goal_2}}.
- {{goal_3}}.
- Backward-compatibility: results JSONs predating this change SHALL render unchanged (the new field is absent / defaults to {{default_value}}; the helper guards on `case.get(...)` rather than `case[...]`).

**Non-Goals:**

- {{non_goal_1}}.
- {{non_goal_2}}.
- {{non_goal_3_optional}}.

## Decisions

### Decision 1: {{decision_1_title}}

{{decision_1_body}}

**Alternative considered**: {{decision_1_alternative}}. Rejected because {{decision_1_rejection_reason}}.

### Decision 2: {{decision_2_title}}

{{decision_2_body}}

### Decision 3: {{decision_3_title_optional}}

{{decision_3_body_optional}}

## Risks / Trade-offs

- **{{risk_1_title}}** — {{risk_1_body_and_mitigation}}.
- **{{risk_2_title}}** — {{risk_2_body_and_mitigation}}.

## Open Questions

{{open_questions_or_none}}
