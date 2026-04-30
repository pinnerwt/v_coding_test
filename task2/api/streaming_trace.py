from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from agent.trace import AnyEvent, TraceWriter

logger = logging.getLogger(__name__)


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
        super().append_event(event)
        if self._on_event is None:
            return
        try:
            self._on_event(event.model_dump(mode="json"))
        except Exception:
            logger.exception("streaming subscriber raised; suppressing")
