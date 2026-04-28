## ADDED Requirements

### Requirement: Tier-1 curated dataset vendored at canonical path
The file `task2/eval/bench/data/webvoyager/tier1.json` SHALL exist and contain exactly 12 WebVoyager task entries. Each entry SHALL conform to the upstream schema: an object with fields `id` (string), `web_name` (string), `ques` (string), `web` (string URL).

The 12 entries SHALL cover the following stable, popup-free, login-free domains:
Wikipedia (2 tasks), arXiv (2 tasks), GitHub (2 tasks), HuggingFace (2 tasks), BBC News (2 tasks), Cambridge Dictionary (1 task), Wolfram Alpha (1 task).

Excluded domains (MUST NOT appear in the Tier-1 file): Allrecipes, Apple, Coursera, Google Search, Booking.com, Google Flights, Amazon. These are excluded because they require login, CAPTCHA, or location-aware widgets that make results non-deterministic.

#### Scenario: Tier-1 file is valid JSON with exactly 12 entries
- **WHEN** `tier1.json` is loaded with `json.load`
- **THEN** it returns a list of length exactly 12 with no parse errors

#### Scenario: Each Tier-1 entry has the required upstream schema fields
- **WHEN** iterating the 12 entries in `tier1.json`
- **THEN** each entry has keys `id`, `web_name`, `ques`, `web`

#### Scenario: No excluded domains appear in Tier-1
- **WHEN** reading all `web_name` values from `tier1.json`
- **THEN** none of `["Allrecipes", "Apple", "Coursera", "Google", "Booking", "Amazon"]` appear

### Requirement: load_webvoyager deserialises Tier-1 file into 12 valid Case dicts
Calling `load_webvoyager("task2/eval/bench/data/webvoyager/tier1.json")` SHALL return a list of exactly 12 dicts, each with valid `task`, `domain`, `category`, `id`, `expect`, `budget`, and `fixture` fields. The `load_webvoyager` function's implementation SHALL NOT be modified; this requirement validates the dataset conforms to the existing loader contract.

#### Scenario: Loader returns 12 cases from Tier-1 file
- **WHEN** `load_webvoyager` is called with the Tier-1 file path
- **THEN** the return value is a list of length 12

#### Scenario: All Tier-1 cases have non-empty task and domain
- **WHEN** iterating the 12 cases returned by the loader
- **THEN** each case has a non-empty `task` string and a non-empty `domain` string

#### Scenario: All Tier-1 case IDs start with webvoyager-
- **WHEN** iterating the 12 cases returned by the loader
- **THEN** each case `id` starts with `"webvoyager-"`

### Requirement: WebVoyager benchmark site-selection rationale documented in README
The `task2/README.md` file SHALL contain a "WebVoyager benchmark" section (or subsection) that documents:
- The distinction between Tier-0 (3 tasks, smoke-test fixture) and Tier-1 (12 tasks, per-branch regression signal).
- The criteria for site inclusion: stable layout, no login required, no CAPTCHA, no location-aware widgets.
- The list of excluded domains and the reason for each exclusion.
- The Tier-0 baseline results (date, pass rate, per-task steps and cost) as recorded in `task2/benchmark/task2-benchmarks-readme-and-tier0/webvoyager/baseline.json`.

#### Scenario: README contains WebVoyager benchmark section
- **WHEN** `task2/README.md` is read
- **THEN** it contains the text "WebVoyager" and at least one of "Tier-0" or "Tier-1"

#### Scenario: README documents excluded domains
- **WHEN** `task2/README.md` is read
- **THEN** it contains at least one excluded domain name from the list (e.g. "Allrecipes", "Coursera", "Amazon")
