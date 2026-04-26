FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

ENV UV_SYSTEM_PYTHON=1
ENV UV_NO_MANAGED_PYTHON=1

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --no-dev --frozen

COPY agent/ agent/
COPY api/ api/

RUN .venv/bin/playwright install chromium --with-deps

EXPOSE 8000

CMD [".venv/bin/uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
