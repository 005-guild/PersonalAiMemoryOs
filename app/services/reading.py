"""Collection reading never initializes configuration, publishes files, or calls models."""

import re
from pathlib import Path
from app.models import OrganizationControl
from app.repositories.reading import ReadingRepository
from app.services.content import ContentError, knowledge_snapshot
from app.services.organization.publication import ASSET_PREFIX
from app.services.zhihu_sync.storage import safe_path


class ReadingService:
    def __init__(self, store):
        self.store = store

    def overview(self):
        with self.store.transaction() as session:
            return ReadingRepository(session).overview()

    def notes(self, **filters):
        with self.store.transaction() as session:
            return ReadingRepository(session).notes(**filters)

    def detail(self, identifier):
        with self.store.transaction() as session:
            pair, eligible = ReadingRepository(session).detail(identifier)
            if not pair:
                raise ContentError(404, 'reading_not_found')
            if not eligible:
                raise ContentError(409, 'reading_not_ready')
            item, note = pair
            control = session.get(OrganizationControl, 1)
            output = control.value.get('config', {}).get('output_dir', '') if control else ''
            images = self._images(item.snapshot.get('images', []), output)
            original = item.snapshot['values']
            return {'note': knowledge_snapshot(note),
                    'original': {key: original.get(key) for key in ('title', 'author', 'url', 'content')},
                    'images': images,
                    'partial_image_summary': bool((item.result or {}).get('partial_image_summary'))}

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
