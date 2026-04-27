## MODIFIED Requirements

### Requirement: ObservationEvent model

The system SHALL provide `agent.trace.ObservationEvent(EventBase)` with `kind: Literal["observation"]` and these additional fields:

- `url: str` — current page URL.
- `title: str` — current page title.
- `ax_tree_digest: str` — trimmed AX tree shown to the LLM (exact prompt input).
- `ax_fingerprint: str` — hash for drift detection.
- `screenshot_ref: str` — path or blob ID; not inlined.
- `viewport: dict` — keys `w: int`, `h: int`.
- `last_actions: list[dict]` — ordered list of actions dispatched since the previous observation. Each entry SHALL have keys `tool: str`, `intent: str`, `outcome: Literal["ok", "error"]`, and optionally `error: str` when `outcome == "error"`. Defaults to `[]` (empty list) when no actions were taken (e.g. first step).

#### Scenario: ObservationEvent round-trips through JSON

- **WHEN** an `ObservationEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

#### Scenario: ObservationEvent accepts last_actions list with entries

- **WHEN** an `ObservationEvent` is constructed with `last_actions=[{"tool": "goto", "intent": "{'url': 'http://x.com'}", "outcome": "ok"}]`
- **THEN** construction SHALL succeed
- **AND** `event.last_actions[0]["tool"]` SHALL equal `"goto"`
- **AND** the JSON round-trip SHALL preserve the `last_actions` list

#### Scenario: ObservationEvent defaults last_actions to empty list

- **WHEN** an `ObservationEvent` is constructed without supplying `last_actions`
- **THEN** `event.last_actions` SHALL equal `[]`
- **AND** the serialized JSON SHALL contain `"last_actions": []`

#### Scenario: ObservationEvent last_actions entry with error outcome round-trips

- **WHEN** an `ObservationEvent` is constructed with `last_actions=[{"tool": "read", "intent": "Submit button", "outcome": "error", "error": "Error: could not locate element"}]`
- **THEN** the JSON round-trip SHALL preserve the `"error"` key in the entry
- **AND** `event.last_actions[0]["outcome"]` SHALL equal `"error"`
