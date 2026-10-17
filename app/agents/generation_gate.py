"""One process-wide text-generation slot shared by drafts and question answering."""

from threading import BoundedSemaphore


class GenerationGate:
    def __init__(self) -> None:
        self._semaphore = BoundedSemaphore(1)

    def acquire(self, blocking: bool = False) -> bool:
        return self._semaphore.acquire(blocking=blocking)

    def release(self) -> None:
        self._semaphore.release()
