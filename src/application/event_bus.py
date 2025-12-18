import asyncio
from typing import Dict, Type, List, Callable, Awaitable, Optional
from collections import defaultdict


class EventBus:
    """Pub/sub backbone with optional per-key ordering."""

    def __init__(self):
        self._handlers: Dict[Type, List[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._ordered_queues: Dict[str, asyncio.Queue] = {}
        self._ordered_tasks: Dict[str, asyncio.Task] = {}
        self._running = False

    def subscribe(
        self,
        event_type: Type["Event"],
        handler: Callable[["Event"], Awaitable[None]],
    ):
        """Subscribe handler to event type."""
        self._handlers[event_type].append(handler)

    async def publish(self, event: "Event", sequence_key: Optional[str] = None):
        """Publish event; when sequence_key is provided, preserve ordering per key."""
        if sequence_key:
            if sequence_key not in self._ordered_queues:
                queue = asyncio.Queue()
                self._ordered_queues[sequence_key] = queue
                self._ordered_tasks[sequence_key] = asyncio.create_task(
                    self._run_ordered(sequence_key)
                )
            await self._ordered_queues[sequence_key].put(event)
        else:
            await self._queue.put(event)

    async def run(self):
        """Process events from default queue."""
        self._running = True
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue

    async def stop(self):
        """Stop the bus and all ordered workers."""
        self._running = False
        for task in self._ordered_tasks.values():
            task.cancel()
        await asyncio.gather(*self._ordered_tasks.values(), return_exceptions=True)
        self._ordered_tasks.clear()
        self._ordered_queues.clear()

    async def _run_ordered(self, key: str):
        """Dedicated loop per sequence key to keep ordering stable."""
        queue = self._ordered_queues[key]
        while self._running:
            try:
                event = await queue.get()
                await self._dispatch(event)
            except asyncio.CancelledError:
                break

    async def _dispatch(self, event: "Event"):
        event_type = type(event)
        for handler in self._handlers.get(event_type, []):
            try:
                await handler(event)
            except Exception as exc:
                # In production replace with structured logging
                print(f"Handler error for {event_type}: {exc}")

