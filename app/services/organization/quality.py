"""Version-checked summary candidates over existing collection records."""
import json
from sqlalchemy import select
from app.models import Knowledge, OrganizationItem, OrganizationJob
from app.services.content import ContentService, knowledge_snapshot
from app.services.organization.contracts import OrganizationError, fingerprint
from app.services.organization.quality_contract import validate, markdown
from app.services.organization.publication import body
from app.paths import resource_root


def sample(snapshot, result):
    observations = result.get('image_observations', [])
    clear = [dict(row, id=f'O{index+1}') for index, row in enumerate(observations) if not row.get('uncertain')]
    visual = snapshot['text_chars'] < 200 and bool(snapshot['images'])
    if visual and (not clear or {x['image'] for x in observations} != {x['reference'] for x in snapshot['images']}):
        raise OrganizationError('image_needs_review')
    return {'original': snapshot['values'], 'observations': clear, 'image_only': visual,
            'partial': bool(result.get('partial_image_summary'))}


def prompt():
    return (resource_root() / 'app/prompts/collection_quality_pilot_v1.md').read_text(encoding='utf-8')


def payload(value):
    return json.dumps({'title': value['original']['title'], 'author': value['original'].get('author'),
        'content': value['original']['content'], 'clear_image_observations': value['observations'],
        'partial_image_input': value['partial']}, ensure_ascii=False)


def verify_original(snapshot, config):
    from app.services.organization.inventory import inspect_directory
    current = next((row for row in inspect_directory(config['input_dir']) if row['identity'] == snapshot['identity']), None)
    if not current or current['input_hash'] != snapshot['input_hash']:
        raise OrganizationError('source_changed')


class QualityService:
    def __init__(self, organization):
        self.organization = organization
        self.store = organization.store

    def view(self, identifier):
        with self.store.transaction() as session:
            item = session.scalar(select(OrganizationItem).where(OrganizationItem.knowledge_id == identifier))
            note = session.get(Knowledge, identifier)
            if not item or not note or note.deleted_at:
                raise OrganizationError('reading_not_found')
            candidate = (item.result or {}).get('quality_candidate')
            estimate = None
            if self.organization.calls.registry is not None:
                from app.services.organization.providers import price_snapshot, cost
                config = self.store.control(session)['config']
                try:
                    resolved = self.organization.calls.resolve(config)
                    incoming = len((prompt()+payload(sample(item.snapshot,item.result))).encode('utf-8'))+1024
                    estimate = cost(price_snapshot(resolved),incoming,resolved.profile.max_output_tokens)/1_000_000
                except OrganizationError:
                    pass
            return {'current': knowledge_snapshot(note), 'candidate': candidate,
                    'estimated_yuan':estimate, 'previous':(item.result or {}).get('quality_previous'),
                    'adopted': (item.result or {}).get('quality_adopted'),
                    'stale': bool(candidate and (candidate['base_version'] != note.version or candidate['input_hash'] != item.input_hash))}

    def start(self, identifier, expected_version):
        self.organization.writable()
        self.store.scan()
        with self.store.transaction() as session:
            self.store.require_idle(session)
            item = session.scalar(select(OrganizationItem).where(OrganizationItem.knowledge_id == identifier))
            note = session.get(Knowledge, identifier)
            if not item or not note or note.deleted_at or item.status != 'published' or item.error:
                raise OrganizationError('reading_not_ready')
            ContentService(session).require_version(note, expected_version)
            if (item.result or {}).get('quality_candidate', {}).get('base_version') == note.version:
                return {'status': 'ready'}
            control = self.store.control(session)
            if control['paused']:
                raise OrganizationError('organization_paused')
            config = dict(control['config'])
            resolved = self.organization.calls.resolve(config)
            job = OrganizationJob(mode='quality', selection=[item.id], settings={**config,
                'initial_period': False, 'base_version': note.version, 'profile_fingerprint': resolved.fingerprint})
            session.add(job); session.flush()
            return {'id': job.id, 'status': job.status}

    async def run(self, job_id):
        with self.store.transaction() as session:
            job = session.get(OrganizationJob, job_id)
            item = session.get(OrganizationItem, job.selection[0])
            original_hash = item.input_hash
            value = sample(item.snapshot, item.result)
            expected_version = job.settings['base_version']
        candidate = await self.organization.calls.generate(job_id, item.id, 'quality-v1', prompt(), payload(value),
            lambda raw: validate(json.dumps(raw, ensure_ascii=False), value))
        with self.store.transaction() as session:
            current = session.get(OrganizationItem, item.id)
            if current.input_hash != original_hash or current.error:
                raise OrganizationError('source_changed')
            current.result = {**current.result, 'quality_candidate': {
                'id': fingerprint({'candidate': candidate, 'input_hash': original_hash, 'version': expected_version}),
                'base_version': expected_version, 'input_hash': original_hash, 'value': candidate,
                'markdown': markdown(candidate), 'provenance': {'job_id': job_id}}}

    def adopt(self, identifier, expected_version, candidate_id):
        self.organization.writable()
        with self.store.transaction() as session:
            self.store.require_idle(session)
            item = session.scalar(select(OrganizationItem).where(OrganizationItem.knowledge_id == identifier))
            note = session.get(Knowledge, identifier)
            if not item or not note or note.deleted_at or item.error:
                raise OrganizationError('reading_not_ready')
            result = dict(item.result or {})
            if result.get('quality_adopted', {}).get('id') == candidate_id:
                return knowledge_snapshot(note)
            candidate = result.get('quality_candidate')
            if not candidate or candidate['id'] != candidate_id or candidate['input_hash'] != item.input_hash:
                raise OrganizationError('quality_candidate_changed')
            if candidate['base_version'] != expected_version:
                raise OrganizationError('quality_candidate_changed')
            ContentService(session).require_version(note, expected_version)
            verify_original(item.snapshot, self.store.control(session)['config'])
            original = self.organization.publication.assets(item.snapshot, self.store.control(session)['config'])
            result['quality_previous'] = knowledge_snapshot(note)
            result['detail'] = candidate['value']
            ContentService(session).update_knowledge(identifier, expected_version,
                {'summary': candidate['value']['summary'], 'body': body(item.snapshot, result, original)})
            result['quality_adopted'] = {'id': candidate_id, 'version': note.version, 'provenance': candidate['provenance']}
            result.pop('quality_candidate', None)
            item.result = result
            config = dict(self.store.control(session)['config'])
        # File publication is restart-safe and conflict checked by the existing exporter.
        self.organization.publication.export(item.id, config)
        return self.view(identifier)
