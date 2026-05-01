"""Prometheus metrics surface.

Centralizes the metric definitions so a route handler or the access-log
middleware can call `record_request(...)` without re-importing
`prometheus_client` everywhere. The default registry is shared across
the process; tests should not reset it (counters monotonically grow,
which is the contract Prometheus assumes).

Cardinality discipline: the `route` label uses the templated path
(e.g. `/tasks/{run_id}`), never the raw request path with the run_id
substituted in — substituting would make every run a new label set
and exhaust memory. The middleware passes the templated form when the
route matched; falls back to a literal-but-bucketed path for
unmatched routes (404s) so the cardinality stays bounded.
"""

from __future__ import annotations

import threading

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

http_requests_total = Counter(
    "http_requests_total",
    "Count of HTTP requests handled, labeled by route template, method, and status code.",
    labelnames=("route", "method", "status"),
)

http_request_latency_seconds = Histogram(
    "http_request_latency_seconds",
    "HTTP request handling latency in seconds, labeled by route template and method.",
    labelnames=("route", "method"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def record_request(*, route: str, method: str, status: int, latency_seconds: float) -> None:
    """Single entry-point for HTTP request observability.

    Counter increments by 1; histogram observes one latency sample.
    Status is stringified at the label site (Prometheus labels are
    always strings; doing it here keeps callers simple)."""
    http_requests_total.labels(route=route, method=method, status=str(status)).inc()
    http_request_latency_seconds.labels(route=route, method=method).observe(latency_seconds)


# Task-level metrics: emitted from the terminal-emit path so both
# `/tasks` and `/sessions` flows feed the same series.
tasks_completed_total = Counter(
    "tasks_completed_total",
    "Count of agent runs that reached a terminal event, labeled by terminal status.",
    labelnames=("status",),
)

task_latency_seconds = Histogram(
    "task_latency_seconds",
    "End-to-end agent run latency in seconds, labeled by terminal status.",
    labelnames=("status",),
    # Tasks span seconds-to-minutes; bucket edges chosen for the
    # observed Tier-1 distribution (sub-second up to the 5-minute budget).
    buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 240.0, 360.0, 600.0),
)

tasks_failure_class_total = Counter(
    "tasks_failure_class_total",
    "Count of non-succeeded terminal events, labeled by derived failure class.",
    labelnames=("failure_class",),
)


def _classify_failure(*, status: str, verifier: dict | None) -> str | None:
    """Bucket a non-succeeded terminal into a low-cardinality failure class.

    Picks the first verifier reason key (the leading token before `:`)
    if present — gives buckets like `self_reported_incomplete` or
    `verifier`. Otherwise falls back to the terminal status itself
    (`failed`, `timeout`, `unverified`). Returns None for `succeeded` /
    `done` so callers don't increment the counter on success.
    """
    if status in ("succeeded", "done"):
        return None
    if isinstance(verifier, dict):
        reasons = verifier.get("reasons")
        if isinstance(reasons, list) and reasons:
            first = str(reasons[0])
            head = first.split(":", 1)[0].strip()
            if head:
                return head
    return status or "unknown"


# Cost attribution. Tokens and USD are reported in the LLMCallEvent
# payload streamed through the trace writer's on_event callback —
# every llm_call routes through there, which is the natural seam to
# update Prometheus counters without coupling metrics to the loop.
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Cumulative LLM tokens consumed, labeled by direction.",
    labelnames=("kind",),
)

llm_usd_total = Counter(
    "llm_usd_total",
    "Cumulative LLM USD spend across all runs.",
)


# In-memory cost accumulator. Mirrors the Prometheus counters so the
# `/usage` endpoint can report a process-lifetime snapshot without
# scraping its own metrics or aggregating the trace DB. Persistent
# cost history lives in the trace store; this is the live counter.
_usage_lock = threading.Lock()
_usage_state: dict[str, float] = {
    "prompt_tokens": 0.0,
    "completion_tokens": 0.0,
    "usd": 0.0,
}


def record_llm_call(*, prompt_tokens: int, completion_tokens: int, usd: float) -> None:
    """Record one LLM call's cost contribution.

    Counters are monotonic — never decrement, never reset. A single
    call adds its prompt-side tokens, completion-side tokens, and USD
    to their respective totals.
    """
    if prompt_tokens > 0:
        llm_tokens_total.labels(kind="prompt").inc(prompt_tokens)
    if completion_tokens > 0:
        llm_tokens_total.labels(kind="completion").inc(completion_tokens)
    if usd > 0:
        llm_usd_total.inc(usd)
    with _usage_lock:
        _usage_state["prompt_tokens"] += prompt_tokens
        _usage_state["completion_tokens"] += completion_tokens
        _usage_state["usd"] += usd


def get_usage_snapshot() -> dict[str, float]:
    """Return a snapshot of cumulative token / USD usage in this process.

    The numbers match the `llm_tokens_total` / `llm_usd_total` counter
    increments, but the snapshot is a plain dict so the `/usage` route
    handler doesn't have to reach into prom-client internals.
    """
    with _usage_lock:
        return dict(_usage_state)


def record_task_terminal(
    *,
    status: str,
    latency_seconds: float,
    verifier: dict | None = None,
) -> None:
    """Single entry-point for task observability on terminal emit.

    Increments `tasks_completed_total{status}` and observes
    `task_latency_seconds{status}`. Non-succeeded runs additionally
    increment `tasks_failure_class_total{failure_class}` under a
    verifier-derived bucket (see `_classify_failure`).
    """
    tasks_completed_total.labels(status=status).inc()
    task_latency_seconds.labels(status=status).observe(latency_seconds)
    failure_class = _classify_failure(status=status, verifier=verifier)
    if failure_class is not None:
        tasks_failure_class_total.labels(failure_class=failure_class).inc()


def render_latest() -> tuple[bytes, str]:
    """Render the default registry in Prometheus text-exposition format.

    Returns `(body, content_type)` so the route handler can hand both
    to its response object without importing `prometheus_client`."""
    return generate_latest(), CONTENT_TYPE_LATEST
