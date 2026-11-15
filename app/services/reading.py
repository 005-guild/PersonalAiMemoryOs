"""Collection reading never initializes configuration, publishes files, or calls models."""

import re
from contextlib import contextmanager
from pathlib import Path
from app.models import OrganizationControl
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

    def overview(self):
        with self._snapshot() as session:
            return ReadingRepository(session).overview()

    def notes(self, **filters):
        with self._snapshot() as session:
            return ReadingRepository(session).notes(**filters)

    def detail(self, identifier):
        with self._snapshot() as session:
            pair, eligible = ReadingRepository(session).detail(identifier)
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
        # Filesystem checks stay outside the short database snapshot.
        result['images'] = self._images(images, output)
        return result

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
