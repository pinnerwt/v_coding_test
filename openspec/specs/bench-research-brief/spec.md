# bench-research-brief Specification

## Purpose
TBD - created by archiving change implement-web-bench-integration. Update Purpose after archive.

## Requirements
### Requirement: Research brief exists at expected path
The file `prompts/task2/web-benchmarks.md` SHALL exist in the repository.

#### Scenario: Brief file is present
- **WHEN** the path `prompts/task2/web-benchmarks.md` is checked for existence
- **THEN** the file exists and is non-empty

### Requirement: Brief covers all seven required benchmarks
The research brief SHALL contain a section for each of: WebArena, Mind2Web (including Online-Mind2Web), BrowserGym, WebVoyager, MiniWoB++, WebShop, and the GAIA web subset.

For each benchmark the brief SHALL document:
- License
- Scope (live web, snapshot/replay, or simulated)
- Hosting cost (self-hosted Docker, cloud infra, or none)
- Task format (file type and key fields)
- Headline metric (the primary reported evaluation metric)

#### Scenario: Brief names the selected benchmark
- **WHEN** `prompts/task2/web-benchmarks.md` is read
- **THEN** it contains the text `WebVoyager` and marks it as the selected integration target

#### Scenario: Brief lists all seven benchmarks
- **WHEN** `prompts/task2/web-benchmarks.md` is read
- **THEN** it contains the names `WebArena`, `Mind2Web`, `BrowserGym`, `WebVoyager`, `MiniWoB++`, `WebShop`, and `GAIA`

### Requirement: Brief includes a concrete recommendation with reasoning
The brief SHALL include a recommendation section that names exactly one benchmark to integrate and provides reasoning grounded in at least: license, hosting cost, fit with the agent's `Case` schema, and task format simplicity.

#### Scenario: Recommendation names WebVoyager
- **WHEN** the brief's recommendation section is read
- **THEN** it explicitly names WebVoyager as the selected benchmark with reasoning referencing license, hosting cost, and task format
