"""Live updates for the dashboard: something happened → every open dashboard hears about it.

Phone calls and the try-it page run partly in worker threads, so publish() is thread-safe:
it hands the event to the web server's event loop, which copies it to each subscriber.
In memory, on one server — fine for one instance (noted in the README).

Events never carry phone numbers or caller hashes.
"""

import asyncio
import json
import logging
import time

log = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None
_subscribers: set[asyncio.Queue] = set()
MAX_QUEUE = 200  # a dashboard that stops reading is dropped rather than slowing everyone


def attach_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def publish(kind: str, **data) -> None:
    """Send an event to every open dashboard. Safe to call from any thread."""
    if _loop is None or _loop.is_closed():
        return
    event = {"type": kind, "at": time.time(), **data}
    _loop.call_soon_threadsafe(_fan_out, event)


def _fan_out(event: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            _subscribers.discard(q)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


async def stream(q: asyncio.Queue, heartbeat_s: float = 15.0):
    """Server-Sent Events text for one subscriber, with a heartbeat so proxies keep it open."""
    try:
        yield "retry: 3000\n\n"
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=heartbeat_s)
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    finally:
        unsubscribe(q)
