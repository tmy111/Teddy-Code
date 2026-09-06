"""Thread-to-async streaming bridge for synchronous Engine events."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any


_STREAM_END = object()


class TurnStream:
    """Drive one synchronous turn on a worker thread and queue its events."""

    def __init__(
        self,
        run_turn: Callable[[str], Iterator[dict[str, Any]]],
        message: str,
        on_finished: Callable[["TurnStream"], None],
    ) -> None:
        self._run_turn = run_turn
        self._message = message
        self._on_finished = on_finished
        self._queue: queue.Queue[object] = queue.Queue()
        self._thread = threading.Thread(target=self._drive, daemon=True)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._thread.start()

    def emit(self, event: dict[str, Any]) -> None:
        self._queue.put(dict(event))

    def get(self) -> object:
        return self._queue.get()

    def _drive(self) -> None:
        try:
            for event in self._run_turn(self._message):
                self.emit(event)
        except Exception as exc:
            self.emit(
                {
                    "type": "error",
                    "content": str(exc),
                    "error_type": type(exc).__name__,
                }
            )
        finally:
            self._queue.put(_STREAM_END)
            self._on_finished(self)


def encode_sse(event: dict[str, Any]) -> str:
    """Encode one runtime event without changing its JSON schema."""

    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"event: teddy_event\ndata: {data}\n\n"


async def stream_sse(stream: TurnStream):
    """Yield queued worker events without blocking the FastAPI event loop."""

    while True:
        item = await asyncio.to_thread(stream.get)
        if item is _STREAM_END:
            return
        yield encode_sse(item)
