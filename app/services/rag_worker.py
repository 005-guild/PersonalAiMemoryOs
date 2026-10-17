"""One incremental indexing scheduler; shutdown drains the current cycle."""

import asyncio
import logging

from app.vector.errors import RagError

logger = logging.getLogger(__name__)


class RagWorker:
    def __init__(self, indexer, interval):
        self.indexer, self.interval = indexer, interval
        self.stop_event = asyncio.Event()
        self.task = None

    def start(self):
        self.indexer.worker_running = True
        self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        try:
            while not self.stop_event.is_set():
                try:
                    await self.indexer.run_once()
                except RagError as error:
                    # Stable codes only; a missing key or outage leaves CRUD available.
                    if error.status_code != 429:
                        logger.warning("RAG indexing paused (%s).", error.code)
                except Exception as error:
                    logger.error("RAG indexing cycle failed (%s).", type(error).__name__)
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=self.interval)
                except TimeoutError:
                    pass
        finally:
            self.indexer.worker_running = False

    async def stop(self):
        self.stop_event.set()
        self.indexer.request_stop()
        if self.task is not None:
            await self.task
