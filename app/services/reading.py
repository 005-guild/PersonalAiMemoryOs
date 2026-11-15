"""Collection reading never initializes configuration, publishes files, or calls models."""

import re
from contextlib import contextmanager
from pathlib import Path
from app.models import OrganizationControl, Knowledge, OrganizationItem, Source, SyncState
from sqlalchemy import select
from app.repositories.reading_all import AllReadingRepository
from app.repositories.reading import ReadingRepository
from app.services.content import ContentError, knowledge_snapshot
from app.services.organization.publication import ASSET_PREFIX
from app.services.zhihu_sync.storage import safe_path


class ReadingService:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def _snapshot(self):
        # Background sync holds its process lock while scanning the whole vault.
        # Readers only need SQLite's committed snapshot, not that filesystem lock.
        with self.store.database.session() as session:
            session.autoflush = False
            session.connection().exec_driver_sql('BEGIN')
            yield session  # Session.close rolls back the read transaction.

    def overview(self, scope="collection"):
        with self._snapshot() as session:
            return (ReadingRepository(session).overview() if scope == "collection" else
                    AllReadingRepository(session).overview(scope))

    def notes(self, **filters):
        with self._snapshot() as session:
            return (ReadingRepository(session).notes(**{k:v for k,v in filters.items() if k != "scope"})
                    if filters.get("scope", "collection") == "collection" else AllReadingRepository(session).notes(**filters))

    def detail(self, identifier, scope="collection"):
        with self._snapshot() as session:
            pair, eligible = ReadingRepository(session).detail(identifier)
            if not pair and scope != 'collection':
                return self._ordinary_detail(session, identifier)
            if scope == 'other' and pair:
                raise ContentError(404, 'reading_not_found')
            if not pair:
                raise ContentError(404, 'reading_not_found')
            if not eligible:
                raise ContentError(409, 'reading_not_ready')
            item, note = pair
            control = session.get(OrganizationControl, 1)
            output = control.value.get('config', {}).get('output_dir', '') if control else ''
            images = item.snapshot.get('images', [])
            original = item.snapshot['values']
            result = {'note': knowledge_snapshot(note),
                    'original': {key: original.get(key) for key in ('title', 'author', 'url', 'content')},
                    'partial_image_summary': bool((item.result or {}).get('partial_image_summary'))}
            result['related'] = ReadingRepository(session).related(note)
            result.update(source_kind='collection', sources=[], sync_status='synced', capabilities={'quality': True})
        # Filesystem checks stay outside the short database snapshot.
        result['images'] = self._images(images, output)
        return result

    def _ordinary_detail(self, session, identifier):
        note = session.get(Knowledge, identifier)
        if not note or note.deleted_at:
            raise ContentError(404, 'reading_not_found')
        state = session.get(SyncState, identifier)
        if state and state.status in {'conflict', 'error'}:
            raise ContentError(409, 'reading_not_ready')
        sources = []
        for source_id in note.source_ids:
            source = session.get(Source, source_id)
            if source and not source.deleted_at:
                sources.append({key: getattr(source, key) for key in ('id', 'title', 'author', 'url', 'content')})
        related = AllReadingRepository(session).notes(category=note.category or '', limit=6)['items']
        return {'note': knowledge_snapshot(note), 'original': None, 'sources': sources,
                'source_kind': 'other', 'sync_status': state.status if state else 'pending',
                'capabilities': {'quality': False}, 'images': [], 'partial_image_summary': False,
                'related': [dict(r, reason='同一分类') for r in related if r['knowledge_id'] != note.id][:5]}

    @staticmethod
    def _images(images, output):
        result = []
        for index, image in enumerate(images):
            url = None
            digest = image.get('hash', '')
            if output and re.fullmatch('[a-f0-9]{64}', digest):
                try:
                    root = safe_path(Path(output) / 'assets')
                    for extension in ('.png', '.jpg', '.gif', '.webp'):
                        candidate = safe_path(root / (digest + extension))
                        if candidate.is_relative_to(root) and candidate.is_file():
                            url = ASSET_PREFIX + digest + extension
                            break
                except (OSError, RuntimeError):
                    pass
            result.append({'reference': image.get('reference', ''), 'url': url,
                           'alt': f'原文图片 {index + 1}', 'missing': url is None})
        return result
