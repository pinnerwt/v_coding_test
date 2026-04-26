## ADDED Requirements

### Requirement: zeabur.json declares the service deployment config
`task2/zeabur.json` SHALL be a valid Zeabur service descriptor. It SHALL declare `buildType: "dockerfile"` and reference the Dockerfile path relative to the repo root (`task2/Dockerfile`). It SHALL declare port 8000 as the exposed service port. It SHALL list the required env var keys: `LLM_BASE_URL`, `LLM_MODEL`, and optionally `LLM_API_KEY`. Values for these keys SHALL NOT be hardcoded in the file — they are set via the Zeabur dashboard at deploy time.

#### Scenario: Zeabur picks up Dockerfile path
- **WHEN** Zeabur reads `zeabur.json` from the repo root
- **THEN** it locates `task2/Dockerfile` and uses it as the build source

#### Scenario: Port 8000 is exposed
- **WHEN** the service is deployed on Zeabur
- **THEN** Zeabur routes external traffic to port 8000 inside the container

#### Scenario: LLM_BASE_URL is required at runtime
- **WHEN** the container starts without `LLM_BASE_URL` set
- **THEN** `api/server.py` falls back to `http://localhost:8090` (existing behavior); the Zeabur dashboard MUST override this with the real endpoint URL

### Requirement: README documents deploy instructions and Zeabur URL
`task2/README.md` SHALL contain a deployment section with the docker run command (including all required env vars), the Zeabur URL (initially a placeholder, updated after first deploy), and instructions for setting `LLM_BASE_URL`, `LLM_MODEL`, and `DB_PATH` (for optional persistent volume).

#### Scenario: Docker run command is present in README
- **WHEN** a developer reads `task2/README.md`
- **THEN** they can copy a `docker run` command that starts the service locally with required env vars

#### Scenario: Zeabur URL placeholder is present
- **WHEN** the change is first merged
- **THEN** `task2/README.md` contains a placeholder `ZEABUR_URL` that is replaced with the live URL after the first successful Zeabur deploy
