## ADDED Requirements

### Requirement: Live case YAML schema
Each live case YAML file SHALL conform to the eval case schema (`id`, `domain`, `category`, `task`, `expect`, `budget`) with the addition of `live: true`. A live case SHALL NOT set `fixture: true`. The `live: true` field is informational; the runner's skip logic is driven by the absence of `fixture: true`.

#### Scenario: Live case YAML loads without error
- **WHEN** `load_cases("eval/cases/live-<name>.yaml")` is called for any of the five live case files
- **THEN** it returns a list with one dict containing all required fields (`id`, `domain`, `category`, `task`, `expect`, `budget`) and `live == True`

#### Scenario: Live case YAML has no fixture flag
- **WHEN** any live case YAML is loaded
- **THEN** `case.get("fixture", False)` is `False`

### Requirement: Search-and-extract live case
The file `task2/eval/cases/live-search-extract.yaml` SHALL define a case targeting `en.wikipedia.org` with `category: search-and-extract`. The task SHALL instruct the agent to navigate to the Python programming language Wikipedia article and return the first sentence of the lead paragraph as `summary`. The validator SHALL assert `summary.nonempty`. The budget SHALL be `steps: 20, usd: 0.25, seconds: 120`.

#### Scenario: Wikipedia search-and-extract case structure
- **WHEN** `load_cases("eval/cases/live-search-extract.yaml")` is called
- **THEN** the result has `id == "live-search-extract"`, `domain == "en.wikipedia.org"`, `category == "search-and-extract"`, `live == True`, `budget == {"steps": 20, "usd": 0.25, "seconds": 120}`, and `expect.validators` contains `"summary.nonempty"`

### Requirement: Form-fill live case
The file `task2/eval/cases/live-form-fill.yaml` SHALL define a case targeting `duckduckgo.com` with `category: form-fill`. The task SHALL instruct the agent to navigate to DuckDuckGo, search for "Python programming language", and return the title of the first result as `first_result_title`. The validator SHALL assert `first_result_title.nonempty`. The budget SHALL be `steps: 20, usd: 0.25, seconds: 120`.

#### Scenario: DuckDuckGo form-fill case structure
- **WHEN** `load_cases("eval/cases/live-form-fill.yaml")` is called
- **THEN** the result has `id == "live-form-fill"`, `domain == "duckduckgo.com"`, `category == "form-fill"`, `live == True`, and `expect.validators` contains `"first_result_title.nonempty"`

### Requirement: Multi-page navigation live case
The file `task2/eval/cases/live-multi-page-nav.yaml` SHALL define a case targeting `books.toscrape.com` with `category: multi-page-nav`. The task SHALL instruct the agent to navigate to the Books to Scrape catalogue, go to page 2, and return the title of the first book listed as `book_title`. The validator SHALL assert `book_title.nonempty`. The budget SHALL be `steps: 30, usd: 0.30, seconds: 150`.

#### Scenario: Books to Scrape multi-page-nav case structure
- **WHEN** `load_cases("eval/cases/live-multi-page-nav.yaml")` is called
- **THEN** the result has `id == "live-multi-page-nav"`, `domain == "books.toscrape.com"`, `category == "multi-page-nav"`, `live == True`, `budget.steps == 30`, and `expect.validators` contains `"book_title.nonempty"`

### Requirement: Conditional-pick live case
The file `task2/eval/cases/live-conditional-pick.yaml` SHALL define a case targeting `books.toscrape.com` mystery category with `category: conditional-pick`. The task SHALL instruct the agent to navigate to `https://books.toscrape.com/catalogue/category/books/mystery_3/index.html`, find the first book with a five-star rating, and return its title as `book_title`. The validator SHALL assert `book_title.nonempty`. The budget SHALL be `steps: 25, usd: 0.30, seconds: 150`.

#### Scenario: Conditional-pick case structure
- **WHEN** `load_cases("eval/cases/live-conditional-pick.yaml")` is called
- **THEN** the result has `id == "live-conditional-pick"`, `domain == "books.toscrape.com"`, `category == "conditional-pick"`, `live == True`, and `expect.validators` contains `"book_title.nonempty"`

### Requirement: Read-and-summarize live case
The file `task2/eval/cases/live-read-summarize.yaml` SHALL define a case targeting `docs.python.org` with `category: read-and-summarize`. The task SHALL instruct the agent to navigate to `https://docs.python.org/3/library/pathlib.html` and return the first paragraph of the module description as `summary`. The validator SHALL assert `summary.nonempty`. The budget SHALL be `steps: 20, usd: 0.25, seconds: 120`.

#### Scenario: Python docs read-and-summarize case structure
- **WHEN** `load_cases("eval/cases/live-read-summarize.yaml")` is called
- **THEN** the result has `id == "live-read-summarize"`, `domain == "docs.python.org"`, `category == "read-and-summarize"`, `live == True`, and `expect.validators` contains `"summary.nonempty"`

### Requirement: Live gating tests
`task2/tests/test_live_gating.py` SHALL contain tests that verify runner gating behavior for live cases using mocked loop and browser. No real HTTP requests SHALL be made in these tests.

#### Scenario: Live case skipped without --live flag
- **WHEN** `run_suite(cases=[<live_case>], results_dir=tmp_path, live=False)` is called with a case that has no `fixture: true`
- **THEN** the results JSON contains exactly one entry with `status == "skipped"`, `steps == 0`, `usd == 0.0`, `validators == []`

#### Scenario: Live case executed with --live flag
- **WHEN** `run_suite(cases=[<live_case>], results_dir=tmp_path, live=True)` is called with a patched loop returning a canned `RunResult`
- **THEN** the results JSON contains exactly one entry with the status from the canned `RunResult` (not `"skipped"`)

#### Scenario: Mixed suite respects gating per case
- **WHEN** `run_suite(cases=[<fixture_case>, <live_case>], results_dir=tmp_path, live=False)` is called
- **THEN** the fixture case entry has a non-skipped status and the live case entry has `status == "skipped"`

#### Scenario: All five live cases load without error
- **WHEN** all five `live-*.yaml` files are loaded via `load_cases`
- **THEN** each returns a valid case dict with all required fields and `fixture` absent or `False`

### Requirement: README live results section
`task2/README.md` SHALL contain a "Live eval results" section with a table documenting the last manual `--live` run results. The table SHALL include columns for case ID, target site, status (succeeded/failed/skipped/timeout), steps used, and notes. The section SHALL be present even if results have not yet been recorded (placeholder row is acceptable before the first run).

#### Scenario: README contains live results section
- **WHEN** `task2/README.md` is read
- **THEN** it contains a section header matching "Live eval results" (case-insensitive)

#### Scenario: README results table has required columns
- **WHEN** the live results section is present
- **THEN** the table has at minimum the columns: case, site, status, steps, notes
