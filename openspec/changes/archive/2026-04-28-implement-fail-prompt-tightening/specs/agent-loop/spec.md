## ADDED Requirements

### Requirement: System prompt fail guidance content

The string returned by `_build_system_prompt` SHALL contain `fail`-gate guidance that:

1. Uses the phrase `"ONLY for irrecoverable conditions"` to gate when `fail` is appropriate.
2. Names the accepted irrecoverable conditions: login walls, captchas, pages that don't exist, or required information genuinely absent from the page.
3. Instructs the model to attempt `click`/`type` with a natural-language `intent` first when a target element exists on the page but the action is uncertain, noting that the locator pipeline will resolve it.

The old unconditional phrasing ("If you cannot complete the task, call `fail` with a reason.") SHALL NOT appear in the returned string.

#### Scenario: system prompt contains ONLY-for phrasing

- **WHEN** `_build_system_prompt("any task")` is called
- **THEN** the returned string SHALL contain the substring `"ONLY for irrecoverable conditions"`

#### Scenario: system prompt contains action-first guidance

- **WHEN** `_build_system_prompt("any task")` is called
- **THEN** the returned string SHALL contain the substring `"attempt \`click\`/\`type\`"`

#### Scenario: system prompt does not contain unconditional fail invitation

- **WHEN** `_build_system_prompt("any task")` is called
- **THEN** the returned string SHALL NOT contain the substring `"If you cannot complete the task, call"`

#### Scenario: system prompt names irrecoverable conditions

- **WHEN** `_build_system_prompt("any task")` is called
- **THEN** the returned string SHALL contain the substrings `"login walls"`, `"captchas"`, `"pages that don't exist"`, and `"required information genuinely absent from the page"`
