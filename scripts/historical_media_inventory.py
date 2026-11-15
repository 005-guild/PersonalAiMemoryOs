"""Read-only historical image health, deterministic coverage and protected fingerprints."""

import hashlib
from pathlib import Path

from PIL import Image, ImageSequence

from app.services.organization.inventory import inspect_directory
from app.services.zhihu_sync.storage import safe_path


def files_snapshot(folder, *, timestamps=False):
    folder = safe_path(Path(folder))
    result = {}
    for path in sorted(folder.rglob('*')):
        path = safe_path(path)
        if not path.is_relative_to(folder):
            raise ValueError('snapshot_path_escape')
        if path.is_file():
            with path.open('rb') as stream:
                value = hashlib.file_digest(stream, 'sha256').hexdigest()
            result[path.relative_to(folder).as_posix()] = (
                [value, path.stat().st_mtime_ns] if timestamps else value)
    return result


def protected_snapshot(runtime, original):
    runtime, original = Path(runtime), Path(original)
    result = {name: files_snapshot(path) for name, path in {
        'originals': original, 'completion_ledger': original.parent / '.sync',
        'organized_mirror': original.parent / '整理库', 'vault': runtime / 'knowledge',
        'configuration': runtime / 'config',
    }.items()}
    result['database_and_environment'] = {}
    for name in ('data/memory.db', '.env'):
        path = safe_path(runtime / name)
        if path.is_file():
            with path.open('rb') as stream:
                result['database_and_environment'][name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def image_health(path):
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('image_too_large')
    with Image.open(path) as image:
        width, height = image.size
        if width * height > 40_000_000:
            raise ValueError('image_too_large')
        kind = image.format
        animated = bool(getattr(image, 'is_animated', False))
        image.verify()
    frames = 0
    with Image.open(path) as image:
        for frame in ImageSequence.Iterator(image):
            if frame.width * frame.height > 40_000_000:
                raise ValueError('image_too_large')
            frame.load()
            frames += 1
    return {'width': width, 'height': height, 'format': kind, 'animated': animated, 'frames': frames}


def audit_inventory(root):
    root = safe_path(Path(root))
    entries = inspect_directory(root)
    errors, health, referenced, physical = [], {}, set(), set()
    for entry in entries:
        for image in entry['images']:
            if image.get('error'):
                errors.append({'identity': entry['identity'], 'code': image['error']})
            elif image.get('relative_path'):
                referenced.add(image['relative_path'])
    for candidate in sorted((root / 'images').rglob('*')):
        path = safe_path(candidate)
        if not path.is_relative_to(root):
            raise ValueError('image_path_escape')
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        physical.add(relative)
        try:
            health[relative] = image_health(path)
        except Exception as error:
            errors.append({'path': relative, 'code': type(error).__name__})
    for entry in entries:
        # Count distinct image content, not duplicate Markdown references.
        entry['distinct_images'] = len({i['hash'] for i in entry['images'] if i.get('hash')})
        entry['long_image'] = any(max(health.get(i.get('relative_path'), {}).get(k, 0) for k in ('width', 'height')) > 8192
                                  for i in entry['images'])
        entry['image_centric'] = entry['resource_type'] == 'answer' and entry['text_chars'] < 200 and bool(entry['images'])
    summary = {'articles': len(entries), 'articles_with_images': sum(bool(e['images']) for e in entries),
        'referenced_unique_images': len(referenced), 'physical_image_files': len(physical), 'healthy_images': len(health),
        'animated_files': sum(h['animated'] for h in health.values()),
        'decoded_frames': sum(h['frames'] for h in health.values()),
        'unreferenced_files': sorted(physical - referenced), 'errors': errors}
    return entries, summary


def matches(entry, case):
    if case == 'long_image':
        return entry['long_image']
    if case == 'image_centric':
        return entry['image_centric']
    kind, group = case.split('.')
    return entry['resource_type'] == kind and (
        entry['distinct_images'] == 1 if group == 'single' else entry['distinct_images'] >= 2)


def select_cases(entries, available=None):
    candidates = [e for e in entries if e['images'] and (available is None or e['identity'] in available)]
    selected, coverage = {}, []
    cases = [kind + '.' + group for kind in ('answer', 'article', 'pin') for group in ('single', 'multiple')]
    for case in [*cases, 'long_image', 'image_centric']:
        eligible = [e for e in selected.values() if matches(e, case)]
        eligible = eligible or [e for e in candidates if matches(e, case)]
        if not eligible:
            raise RuntimeError('coverage_missing:' + case)
        entry = min(eligible, key=lambda e: (e['distinct_images'], int(e['external_id'])))
        selected[entry['identity']] = entry
        coverage.append({'case': case, 'identity': entry['identity']})
    assert 6 <= len(selected) <= 8
    return list(selected.values()), coverage
