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


def render_latest() -> tuple[bytes, str]:
    """Render the default registry in Prometheus text-exposition format.

    Returns `(body, content_type)` so the route handler can hand both
    to its response object without importing `prometheus_client`."""
    return generate_latest(), CONTENT_TYPE_LATEST
