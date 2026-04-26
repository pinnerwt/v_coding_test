## ADDED Requirements

### Requirement: /score slash skill invokes scripts/score.py

The system SHALL provide a Claude Code slash skill at `.claude/commands/score.md` that, when invoked, runs `uv run python scripts/score.py` from the `task2/` directory with any arguments the user supplies.

The skill SHALL be a thin wrapper: it does not duplicate scoring logic. It MAY provide a brief description of acceptable arguments (`results_file`, `--update-readme`, `--readme-path`).

#### Scenario: /score skill file exists at expected path

- **WHEN** `.claude/commands/score.md` is inspected
- **THEN** it SHALL exist and contain a `uv run python scripts/score.py` invocation

#### Scenario: /score skill does not duplicate scoring logic

- **WHEN** `.claude/commands/score.md` content is read
- **THEN** it SHALL NOT contain any percentile computation, markdown generation, or file-parsing logic
- **AND** the total line count SHALL be fewer than 30 lines
