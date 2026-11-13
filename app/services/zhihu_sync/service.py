"""Single-thread browser ownership, non-overlapping polling, cooperative shutdown."""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Event, RLock, Thread
import time

from app.services.zhihu_sync.configuration import Configuration
from app.services.zhihu_sync.runner import run_collection
from app.services.zhihu_sync.storage import SyncError


@contextmanager
def open_browser(root, *, visible, cancelled):
    from app.services.zhihu_sync.browser import ZhihuBrowser
    with ZhihuBrowser(root, visible=visible, cancelled=cancelled) as browser:
        yield browser


class ZhihuSyncService:
    def __init__(self, settings, csrf_token, browser_factory=open_browser):
        self.root, self.csrf_token = settings.runtime_root, csrf_token
        self.read_only = settings.configuration_read_only
        self.configuration = Configuration(self.root)
        self.browser_factory = browser_factory
        self.lock, self.wake, self.shutdown, self.cancel = RLock(), Event(), Event(), Event()
        self.thread = None
        self.command = None
        self.next_run = 0
        self.paused = False
        self.status = {'state':'idle', 'action':None, 'last_error':None, 'last_finished':None, 'report':None}

    def describe(self):
        with self.lock:
            config = self.configuration.load()
            return {**config.model_dump(), 'revision':self.configuration.revision(config),
                    'csrf_token':self.csrf_token, 'editable':not self.read_only,
                    'status':dict(self.status), 'paused':self.paused}

    def save(self, payload):
        with self.lock:
            if self.read_only:
                raise SyncError('configuration_read_only')
            if self.status['state'] in {'queued', 'running'}:
                raise SyncError('sync_busy')
            self.configuration.save(payload)
            self.next_run = 0
            self.wake.set()
            return self.describe()

    def submit(self, action):
        with self.lock:
            if self.read_only or self.shutdown.is_set():
                raise SyncError('sync_unavailable')
            if self.status['state'] in {'queued', 'running'}:
                raise SyncError('sync_busy')
            config = self.configuration.load()
            if not (config.collection_url and config.target_dir):
                raise SyncError('configuration_incomplete')
            self.command = action
            self.status.update(state='queued', action=action, last_error=None, report=None)
            self.cancel.clear()
            self.wake.set()
            return self.describe()

    def stop_current(self):
        self.cancel.set()
        return self.describe()

    def request_stop(self):
        self.shutdown.set()
        self.cancel.set()
        self.wake.set()

    def start(self):
        self.thread = Thread(target=self._loop, name='zhihu-sync', daemon=False)
        self.thread.start()

    async def close(self):
        self.request_stop()
        if self.thread:
            await asyncio.to_thread(self.thread.join)

    def _publish(self, report):
        with self.lock:
            self.status['report'] = report

    def _execute(self, action, config):
        try:
            with self.browser_factory(self.root, visible=action == 'login', cancelled=self.cancel.is_set) as browser:
                if action == 'login':
                    browser.login(config.collection_url)
                    self.paused = False
                else:
                    run_collection(config, browser, self.cancel.is_set, self._publish, preview=action == 'preview')
            self.status['state'] = 'finished'
        except SyncError as error:
            code = str(error)
            self.status.update(state='cancelled' if code == 'cancelled' else 'failed', last_error=code)
            if code in {'login_required', 'verification_required', 'browser_unavailable'}:
                self.paused = True
        except Exception as error:
            # Never expose exception text: browser errors can contain URLs/session state.
            self.status.update(state='failed', last_error='operation_failed')
        finally:
            self.status['last_finished'] = datetime.now(timezone.utc).isoformat()

    def _loop(self):
        while not self.shutdown.is_set():
            with self.lock:
                try:
                    config = self.configuration.load()
                except SyncError:
                    self.status.update(state='failed', last_error='configuration_invalid')
                    config = None
                action, self.command = self.command, None
                if (action is None and config and config.enabled and not self.read_only
                        and not self.paused and time.monotonic() >= self.next_run):
                    action = 'run'
                    self.cancel.clear()
                if action:
                    self.status.update(state='running', action=action, last_error=None, report=None)
            if action and config:
                self._execute(action, config)
                self.next_run = time.monotonic() + (0 if action == 'login' and not self.paused else config.interval_seconds)
            self.wake.wait(timeout=1)
            self.wake.clear()
