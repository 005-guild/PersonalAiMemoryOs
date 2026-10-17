"""One bounded polling task; wait for in-flight IO before database disposal."""

import asyncio
import logging

logger = logging.getLogger(__name__)


class SyncWorker:
    def __init__(self, synchronizer, interval):
        self.synchronizer, self.interval = synchronizer, interval
        self.stop_event = asyncio.Event()
        self.task = None

    def start(self):
        self.synchronizer.worker_running = True
        self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        try:
            while not self.stop_event.is_set():
                try:
                    await asyncio.to_thread(self.synchronizer.run_once)
                except Exception as exc:
                    self.synchronizer.last_error = type(exc).__name__
                    logger.error("Synchronization worker failed (%s).", type(exc).__name__)
                try:
                    await asyncio.wait_for(self.stop_event.wait(), self.interval)
                except TimeoutError:
                    pass
        finally:
            self.synchronizer.worker_running = False

    async def stop(self):
        self.stop_event.set()
        if self.task is not None:
            await self.task  # Do not cancel a to_thread operation still using the engine.
