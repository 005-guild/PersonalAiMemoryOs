"""One durable collection worker with an explicit sample approval checkpoint."""
import asyncio
import logging
from threading import Event
from sqlalchemy import select
from app.models import OrganizationJob, OrganizationItem, utcnow
from app.services.organization.store import Store
from app.services.organization.calls import Calls
from app.services.organization.contracts import OrganizationError, OrganizationSettings, policy
from app.services.organization.generation import taxonomy, summarize
from app.services.organization.publication import Publication

logger = logging.getLogger(__name__)


class OrganizationService:
    def __init__(self, database, lock, settings, registry, client, gate, csrf_token):
        self.store = Store(database, lock, settings.runtime_root)
        self.stopping = Event()
        self.calls = Calls(self.store, registry, client, gate, self.stopping.is_set)
        self.store.resolve_profile=self.calls.resolve
        self.publication = Publication(self.store)
        self.read_only = settings.configuration_read_only
        self.csrf_token = csrf_token
        self.task = None
        self.wake = asyncio.Event()
        self.last_error = None

    def describe(self):
        from app.services.organization.providers import describe
        state=self.store.read()
        available=[]
        for identifier in getattr(self.calls.registry,'profiles',{}):
            try:available.append(describe(self.calls.resolve({**state['config'],'profile_id':identifier})))
            except Exception:pass
        return {**state, 'csrf_token': self.csrf_token,'available_profiles':available,
                'read_only': self.read_only, 'last_error': self.last_error}

    def writable(self):
        if self.read_only or self.stopping.is_set():
            raise OrganizationError('configuration_read_only')

    async def start(self):
        if not self.read_only:
            await asyncio.to_thread(self.store.recover)
            self.task = asyncio.create_task(self._loop())

    def request_stop(self):
        self.stopping.set()

    async def close(self):
        self.request_stop()
        self.wake.set()
        if self.task:
            await self.task

    async def command(self, action, job_id=None):
        self.writable()
        if action == 'scan':
            result = await asyncio.to_thread(self.store.scan)
        elif action in {'sample', 'all', 'retry','continue'}:
            if action in {'sample', 'all'}:
                await asyncio.to_thread(self.store.scan)
            # Reject invalid models/configuration before adding a durable task.
            self.calls.resolve(self.store.read()['config'])
            result = await asyncio.to_thread(self.store.start, action)
        elif action == 'approve':
            result = await asyncio.to_thread(self.store.approve, job_id)
        elif action == 'pause':
            result = await asyncio.to_thread(self.store.pause)
        elif action == 'resume':
            result = await asyncio.to_thread(self.store.resume, job_id)
        elif action == 'cancel':
            result = await asyncio.to_thread(self.store.cancel, job_id)
        elif action == 'retry-sample':
            result = await asyncio.to_thread(self.store.retry_sample, job_id)
        elif action == 'continue-sample':
            result = await asyncio.to_thread(self.store.retry_sample, job_id, False)
        else:
            raise OrganizationError('unknown_action')
        self.wake.set()
        return result

    def _next(self):
        with self.store.transaction() as session:
            if self.store.control(session)['paused']:
                return None
            job = session.scalar(select(OrganizationJob).where(OrganizationJob.status=='pending')
                                 .order_by(OrganizationJob.created_at).limit(1))
            if not job:
                return None
            job.status = 'running'
            return job.id

    async def _loop(self):
        refresh_at = 0
        while not self.stopping.is_set():
            self.wake.clear()
            try:
                identifier = await asyncio.to_thread(self._next)
                if identifier:
                    await self.run_job(identifier)
                    continue
                now = asyncio.get_running_loop().time()
                if now >= refresh_at:
                    refresh_at = now + 60
                    state = await asyncio.to_thread(self.store.read)
                    if state['config']['output_dir'] and not state['paused']:
                        await asyncio.to_thread(self.publication.refresh, state['config'])
                    if state['approved'] and state['config']['enabled'] and not state['paused']:
                        await asyncio.to_thread(self.store.scan)
                        try:
                            await asyncio.to_thread(self.store.start, 'auto')
                            continue
                        except OrganizationError as error:
                            if error.code != 'no_pending_articles':
                                raise
                    self.last_error = None
            except Exception as error:
                self.last_error = error.code if isinstance(error, OrganizationError) else 'organization_failed'
                logger.warning('Collection organization: %s', self.last_error)
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=2)
            except TimeoutError:
                pass

    async def run_job(self, identifier):
        try:
            with self.store.transaction() as session:
                job = session.get(OrganizationJob, identifier)
                selection, config = list(job.selection), dict(job.settings)
                mode = job.mode
                entries = [x.snapshot for x in session.scalars(select(OrganizationItem).order_by(OrganizationItem.identity))]
            if mode == 'quality':
                from app.services.organization.quality import QualityService
                await QualityService(self).run(identifier)
                with self.store.transaction() as session:
                    job = session.get(OrganizationJob, identifier)
                    if job.status == 'running':
                        job.status = 'completed'; job.finished_at = utcnow()
                return
            if not config['taxonomy']:
                config['taxonomy'] = await taxonomy(self.calls, self.store, identifier, entries)
            failures = False
            upstream_failures = 0
            for item_id in selection:
                with self.store.transaction() as session:
                    job = session.get(OrganizationJob, identifier)
                    if self.stopping.is_set() or job.status != 'running':
                        return
                    item = session.get(OrganizationItem, item_id)
                    if item.status=='published' and not item.error:
                        continue
                    if item.error == 'source_changed':
                        failures = True
                        continue
                    result, snapshot = item.result, dict(item.snapshot)
                    sample = job.mode == 'sample'
                try:
                    if not result or result.get('_policy') != policy({k:config[k] for k in OrganizationSettings.model_fields}):
                        result = await summarize(self.calls, identifier, item_id, snapshot, config)
                        result['_policy'] = policy({k:config[k] for k in OrganizationSettings.model_fields})
                        with self.store.transaction() as session:
                            item = session.get(OrganizationItem, item_id)
                            item.result = result
                            item.status = 'ready'
                            item.error = None
                    # A paid call can finish after a pause. Keep its result but do not publish.
                    with self.store.transaction() as session:
                        if self.stopping.is_set() or session.get(OrganizationJob, identifier).status != 'running':
                            return
                    if not sample:
                        await asyncio.to_thread(self.publication.publish, item_id, config)
                    upstream_failures = 0
                except OrganizationError as error:
                    if error.code in {'organization_paused','organization_budget_exhausted','organization_profile_changed'}:
                        raise
                    failures = True
                    with self.store.transaction() as session:
                        item = session.get(OrganizationItem, item_id)
                        item.status = 'failed'; item.error = error.code
                    upstream_failures = upstream_failures+1 if error.code in {'ai_upstream_error','ai_timeout'} else 0
                    if upstream_failures >= 3:
                        raise OrganizationError('organization_upstream_unavailable')
                except Exception:
                    failures = True
                    upstream_failures = 0
                    with self.store.transaction() as session:
                        item = session.get(OrganizationItem, item_id)
                        item.status = 'failed'; item.error = 'organization_failed'
            with self.store.transaction() as session:
                job = session.get(OrganizationJob, identifier)
                if job.status == 'running':
                    job.status = 'completed_with_errors' if failures else 'completed'
                    job.finished_at = utcnow()
                    if job.mode in {'all','auto','retry','continue'} and not failures:
                        control = self.store.control(session)
                        if not session.scalar(select(OrganizationItem.id).where(OrganizationItem.status!='published').limit(1)):
                            control['initial_complete'] = True
                            self.store.set_control(session, control)
        except Exception as error:
            code = error.code if isinstance(error, OrganizationError) else 'organization_failed'
            with self.store.transaction() as session:
                job = session.get(OrganizationJob, identifier)
                if job.status == 'running':
                    job.status = 'paused' if code in {'organization_paused','organization_budget_exhausted','organization_upstream_unavailable'} else 'failed'
                    job.error = code
                    control = self.store.control(session)
                    control['paused'] = True
                    self.store.set_control(session, control)
