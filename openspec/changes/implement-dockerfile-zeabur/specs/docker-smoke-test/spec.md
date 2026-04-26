## ADDED Requirements

### Requirement: Docker smoke test builds image and verifies POST /tasks end-to-end
`task2/tests/test_docker_smoke.py` SHALL contain a pytest test marked `@pytest.mark.docker` that: (1) builds the Docker image from `task2/Dockerfile`, (2) starts a container with a mock LLM server URL and a fixture-serving HTTP server, (3) POSTs to `http://localhost:8000/tasks` with a fixture task body, and (4) asserts the response JSON contains an `id` field. The test SHALL be excluded from the default pytest run; it SHALL only execute when invoked with `pytest -m docker`.

#### Scenario: Test is excluded from default pytest run
- **WHEN** `uv run pytest` is executed without `-m docker`
- **THEN** `test_docker_smoke.py` tests are skipped or not collected

#### Scenario: POST /tasks returns an id
- **WHEN** the smoke test builds the image and POSTs `{"task": "Read the page heading and return it as title", "budget": {"steps": 5, "usd": 0.05, "seconds": 30}}` to the running container's `/tasks` endpoint
- **THEN** the HTTP response status is 200 and the JSON body contains a non-empty `id` string

#### Scenario: Container is torn down after test
- **WHEN** the smoke test completes (pass or fail)
- **THEN** the Docker container is stopped and removed (no dangling containers)

### Requirement: Mock LLM server used in smoke test to avoid live endpoint dependency
The smoke test SHALL start a lightweight mock HTTP server (using `http.server` or `respx` or a `threading.Thread`-based server) that returns a canned valid LLM tool-call response. The `LLM_BASE_URL` env var on the container SHALL point to this mock server (via `host.docker.internal` or the host's bridge IP). This ensures the smoke test is hermetic and does not require a real Qwen3.5 endpoint.

#### Scenario: Mock LLM returns a done tool call
- **WHEN** the agent loop calls the mock LLM endpoint with a chat-completions request
- **THEN** the mock returns a response with a `done` tool call containing a valid `result` and `evidence` payload, causing the agent to finish with status `succeeded` or `unverified`

#### Scenario: Smoke test passes without external network access to LLM
- **WHEN** `LLM_BASE_URL` is set to the mock server and no real LLM is reachable
- **THEN** the smoke test completes and the container run exits cleanly

### Requirement: pytest marker registered for docker tests
`task2/pyproject.toml` SHALL declare a `docker` marker in `[tool.pytest.ini_options]` under `markers`. The default `addopts` SHALL NOT include `-m "not docker"` automatically, but the marker SHALL be registered so `pytest -m docker` is not an unknown-marker warning.

#### Scenario: docker marker is registered
- **WHEN** `uv run pytest --markers` is run from `task2/`
- **THEN** `docker` appears in the list of registered markers
