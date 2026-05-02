from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from agent.trace import AnyEvent, LLMCallEvent, ObservationEvent, TraceWriter

logger = logging.getLogger(__name__)


def _observe_level() -> str:
    """Read OBSERVE_LEVEL fresh per call so an operator can crank it up
    during incident response without redeploying. Default is `info`."""
    return os.environ.get("OBSERVE_LEVEL", "info").lower()


def _sample_for_persistence(event: AnyEvent) -> AnyEvent:
    """Strip large fields from an event when OBSERVE_LEVEL=info.

    Day-to-day operation doesn't need full prompt/response payloads
    or screenshot refs — they bloat the trace store without feeding
    a metric or a dashboard. Incident response flips OBSERVE_LEVEL=debug
    to keep replay-quality traces.

    Streaming consumers (SSE) get the post-sampling form too, so the
    UI doesn't see one shape on disk and another over the wire.
    """
    if _observe_level() == "debug":
        return event
    if isinstance(event, LLMCallEvent):
        return event.model_copy(update={"prompt": {}, "response": {}})
    if isinstance(event, ObservationEvent):
        return event.model_copy(update={"screenshot_ref": ""})
    return event


class StreamingTraceWriter(TraceWriter):
    """TraceWriter that fans out every appended event to an `on_event` callback.

    Subscriber exceptions are swallowed: trace persistence must not fail because
    a downstream consumer (e.g. an SSE subscriber queue) is broken.
    """

    def __init__(
        self,
        path: str = ":memory:",
        *,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(path)
        self._on_event = on_event

    def append_event(self, event: AnyEvent) -> None:
        sampled = _sample_for_persistence(event)
        super().append_event(sampled)
        if self._on_event is None:
            return
        try:
            self._on_event(sampled.model_dump(mode="json"))
        except Exception:
            logger.exception("streaming subscriber raised; suppressing")
