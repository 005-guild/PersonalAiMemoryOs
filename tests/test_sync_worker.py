"""Worker shutdown waits for its real thread instead of cancelling its future."""

import asyncio
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.sync_worker import SyncWorker


def test_worker_stop_waits_for_inflight_scan_before_resource_disposal() -> None:
    entered, release = Event(), Event()
    order = []

    class BlockingSynchronizer:
        worker_running = False

        def run_once(self):
            order.append("scan_started")
            entered.set()
            assert release.wait(timeout=3), "Test did not release the in-flight scan."
            order.append("scan_finished")

    async def scenario():
        synchronizer = BlockingSynchronizer()
        worker = SyncWorker(synchronizer, interval=3600)
        worker.start()
        assert synchronizer.worker_running is True
        assert await asyncio.to_thread(entered.wait, 3)
        stopping = asyncio.create_task(worker.stop())
        await asyncio.sleep(0)
        assert not stopping.done()
        assert synchronizer.worker_running is True
        assert order == ["scan_started"]

        release.set()
        await asyncio.wait_for(stopping, timeout=3)
        order.append("resources_disposed")

        assert synchronizer.worker_running is False
        assert worker.task.done()
        assert order == ["scan_started", "scan_finished", "resources_disposed"]
        await worker.stop()

    try:
        asyncio.run(scenario())
    finally:
        release.set()


def test_worker_stop_during_interval_does_not_start_another_scan() -> None:
    scanned = Event()
    calls = []

    class Synchronizer:
        worker_running = False

        def run_once(self):
            calls.append("scan")
            scanned.set()

    async def scenario():
        synchronizer = Synchronizer()
        worker = SyncWorker(synchronizer, interval=3600)
        worker.start()
        assert await asyncio.to_thread(scanned.wait, 3)
        await asyncio.wait_for(worker.stop(), timeout=3)

        assert calls == ["scan"]
        assert synchronizer.worker_running is False

    asyncio.run(scenario())


def test_stopping_a_worker_that_has_not_started_is_safe() -> None:
    class Synchronizer:
        worker_running = False

    worker = SyncWorker(Synchronizer(), interval=2)
    asyncio.run(worker.stop())

    assert worker.task is None
    assert worker.synchronizer.worker_running is False


def test_application_shutdown_awaits_scan_before_disposing_database(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    enabled = settings.model_copy(update={"sync_enabled": True, "sync_interval": 3600})
    app = create_app(enabled)
    entered, release, ready, request_exit, stopping, disposed = (Event() for _ in range(6))
    errors, order = [], []
    original_stop = app.state.sync_worker.stop
    original_dispose = app.state.database.dispose

    def blocked_scan():
        entered.set()
        assert release.wait(3), "Test did not release the in-flight scan."
        order.append("scan_finished")

    async def observed_stop():
        stopping.set()
        await original_stop()

    def observed_dispose():
        order.append("database_disposed")
        disposed.set()
        original_dispose()

    monkeypatch.setattr(app.state.synchronizer, "run_once", blocked_scan)
    monkeypatch.setattr(app.state.sync_worker, "stop", observed_stop)
    monkeypatch.setattr(app.state.database, "dispose", observed_dispose)

    def serve():
        try:
            with TestClient(app):
                ready.set()
                assert request_exit.wait(3)
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=serve)
    thread.start()
    try:
        assert ready.wait(3)
        assert entered.wait(3)
        request_exit.set()
        assert stopping.wait(3)
        assert not disposed.is_set()
        assert app.state.database.engine is not None
        release.set()
        thread.join(3)

        assert not thread.is_alive()
        assert errors == []
        assert order == ["scan_finished", "database_disposed"]
        assert app.state.database.engine is None
        assert app.state.synchronizer.worker_running is False
    finally:
        release.set()
        request_exit.set()
        thread.join(3)


def test_disabled_worker_remains_idle(client) -> None:
    assert client.app.state.sync_worker.task is None
    assert client.app.state.synchronizer.worker_running is False


def test_application_disposes_database_even_when_worker_stop_raises(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(settings)

    async def failed_stop():
        raise RuntimeError("simulated worker stop failure")

    monkeypatch.setattr(app.state.sync_worker, "stop", failed_stop)

    with pytest.raises(RuntimeError, match="simulated worker stop failure"):
        with TestClient(app):
            assert app.state.database.engine is not None

    assert app.state.database.engine is None
    assert app.state.database.session_factory is None


def test_worker_recovers_from_unexpected_scan_exception_without_stopping(caplog) -> None:
    recovered, release = Event(), Event()
    calls = []

    class RecoveringSynchronizer:
        worker_running = False
        last_error = None

        def run_once(self):
            calls.append("scan")
            if len(calls) == 1:
                raise RuntimeError("private-worker-error-sentinel")
            recovered.set()
            assert release.wait(3)

    async def scenario():
        synchronizer = RecoveringSynchronizer()
        worker = SyncWorker(synchronizer, interval=0)
        worker.start()
        assert await asyncio.to_thread(recovered.wait, 3)
        stopping = asyncio.create_task(worker.stop())
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(stopping, 3)

        assert calls == ["scan", "scan"]
        assert synchronizer.last_error == "RuntimeError"
        assert synchronizer.worker_running is False

    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert "private-worker-error-sentinel" not in caplog.text
