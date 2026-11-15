"""Atomic private artifacts and read-only collection snapshots."""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.repositories.collection_views import ELIGIBLE, INDEXED_FROM
from app.services.organization.contracts import fingerprint
from app.services.zhihu_markdown import _entry


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): result.update(chunk)
    return result.hexdigest()


@contextmanager
def readonly(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON'); connection.execute('BEGIN')
        yield connection
    finally: connection.close()


def select_samples(connection):
    columns = ("SELECT o.id,o.identity,k.category,json_extract(o.snapshot,'$.body_chars') chars,"
               "json_extract(o.snapshot,'$.text_chars') text_chars,"
               "json_array_length(json_extract(o.snapshot,'$.images')) images,"
               "coalesce(json_extract(o.result,'$.partial_image_summary'),0) partial")
    rows = [dict(row) for row in connection.execute(columns + INDEXED_FROM + ' WHERE ' + ELIGIBLE)]
    ordered = sorted(rows, key=lambda row: row['identity'])
    visual = [row for row in ordered if row['text_chars'] < 200 and row['images']]
    visual.sort(key=lambda row: (not row['partial'], row['identity']))
    chosen = [(row, '图片文章') for row in visual[:2]]
    chosen += [(row, '长文') for row in sorted(ordered, key=lambda row: (-row['chars'], row['identity']))
               if row['chars'] > 20000][:2]
    ordinary = [row for row in ordered if row['text_chars'] >= 200 and row['chars'] <= 20000]
    themes = {row['category'].split('/')[0] for row, _ in chosen}
    # Spread the six ordinary samples across themes before taking a second one.
    while ordinary and len(chosen) < 10:
        row = next((row for row in ordinary if row['category'].split('/')[0] not in themes), ordinary[0])
        chosen.append((row, '普通文章')); ordinary.remove(row); themes.add(row['category'].split('/')[0])
    if len(chosen) != 10 or sum(kind == '图片文章' for _, kind in chosen) != 2 or sum(kind == '长文' for _, kind in chosen) != 2:
        raise RuntimeError('pilot_requires_two_long_two_visual_six_ordinary')
    return chosen


def freeze(database, destination):
    with readonly(database) as connection:
        control = json.loads(connection.execute('SELECT value FROM organization_control WHERE id=1').fetchone()[0])
        input_dir = Path(control['config']['input_dir']).resolve()
        samples = []
        for meta, kind in select_samples(connection):
            row = connection.execute('SELECT o.*,k.title,k.summary,k.body,k.category,k.tags,k.version '
                'FROM organization_items o JOIN knowledge k ON k.id=o.knowledge_id WHERE o.id=?', (meta['id'],)).fetchone()
            snapshot = json.loads(row['snapshot']); result = json.loads(row['result'])
            original_file = (input_dir / snapshot['relative_path']).resolve()
            if not original_file.is_relative_to(input_dir): raise RuntimeError('original_path_invalid')
            parsed, _ = _entry(0, {'relative_path':original_file.name,'content':original_file.read_text(encoding='utf-8-sig')}, set())
            if parsed.values != snapshot['values']: raise RuntimeError('original_changed')
            files = {str(original_file): digest(original_file)}
            for image in snapshot.get('images', []):
                path = (input_dir / image['relative_path']).resolve()
                if not path.is_relative_to(input_dir) or digest(path) != image['hash']: raise RuntimeError('image_changed')
                files[str(path)] = image['hash']
            if fingerprint({'values':snapshot['values'],'images':snapshot.get('images',[])}) != row['input_hash']:
                raise RuntimeError('snapshot_hash_mismatch')
            observations = result.get('image_observations', [])
            clear = [dict(value, id=f'O{index+1}') for index, value in enumerate(observations) if not value.get('uncertain')]
            image_only = snapshot['text_chars'] < 200 and bool(snapshot.get('images'))
            error = 'image_observations_missing' if image_only and (not clear or {x['image'] for x in observations} != {x['reference'] for x in snapshot['images']}) else None
            samples.append({'item_id':row['id'],'identity':row['identity'],'knowledge_id':row['knowledge_id'],
                'input_hash':row['input_hash'],'kind':kind,'original':snapshot['values'],
                'current':{key:json.loads(row[key]) if key=='tags' else row[key] for key in ('title','summary','body','category','tags','version')},
                'files':files,'image_only':image_only,'observations':clear if image_only else [],
                'partial':bool(result.get('partial_image_summary')),'prepare_error':error})
    packet = {'schema_version':1,'database':str(Path(database).resolve()),'samples':samples}
    packet['packet_hash'] = fingerprint(packet)
    save(Path(destination)/'samples.json', packet)
    return packet


def verify_sources(packet):
    with readonly(packet['database']) as connection:
        for sample in packet['samples']:
            row = connection.execute('SELECT o.input_hash,k.version,k.title,k.summary,k.body,k.category,k.tags '
                'FROM organization_items o JOIN knowledge k ON k.id=o.knowledge_id WHERE o.id=?', (sample['item_id'],)).fetchone()
            current = sample['current']
            if not row or row['input_hash'] != sample['input_hash'] or any(
                (json.loads(row[key]) if key == 'tags' else row[key]) != value for key,value in current.items()):
                raise RuntimeError('sample_changed_since_freeze')
            if any(digest(path) != expected for path,expected in sample['files'].items()): raise RuntimeError('original_changed_since_freeze')
