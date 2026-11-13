"""Bounded vision inputs; tile oversized images without changing originals."""
import base64
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.services.organization.contracts import OrganizationError
from app.services.zhihu_sync.storage import safe_path

MAX_EDGE = 8192
TILE_EDGE = 2048
OVERLAP = 64


def mime(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png','.png'
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg','.jpg'
    if data.startswith((b'GIF87a',b'GIF89a')): return 'image/gif','.gif'
    if data.startswith(b'RIFF') and data[8:12]==b'WEBP': return 'image/webp','.webp'
    raise OrganizationError('image_format_unsupported')


def tile_boxes(width, height):
    for top in range(0, height, TILE_EDGE - OVERLAP):
        for left in range(0, width, TILE_EDGE - OVERLAP):
            yield (left, top, min(left+TILE_EDGE,width), min(top+TILE_EDGE,height))
            if left+TILE_EDGE >= width:
                break
        if top+TILE_EDGE >= height:
            break


def vision_parts(data, kind):
    try:
        with Image.open(BytesIO(data)) as original:
            if max(original.size) <= MAX_EDGE:
                # Byte-identical small inputs preserve existing paid-response caches.
                yield data, kind, None
                return
            if original.width*original.height > 40_000_000:
                raise OrganizationError('image_too_large')
            if getattr(original, 'is_animated', False):
                raise OrganizationError('image_needs_review')
            original.load()
            for box in tile_boxes(*original.size):
                with original.crop(box) as crop:
                    with crop.convert('RGBA' if 'A' in crop.getbands() or 'transparency' in crop.info else 'RGB') as tile:
                        stream=BytesIO()
                        tile.save(stream,format='PNG')
                        yield stream.getvalue(),'image/png',list(box)
    except Image.DecompressionBombError:
        raise OrganizationError('image_too_large') from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise OrganizationError('image_invalid') from None


def image_inputs(snapshot, directory):
    root=safe_path(Path(directory))
    batch=[]; size=0
    for entry in snapshot['images']:
        if entry.get('error'): raise OrganizationError(entry['error'])
        path=safe_path(root/entry['relative_path'])
        if not path.is_relative_to(root) or path.stat().st_size>20*1024*1024:
            raise OrganizationError('image_too_large')
        data=path.read_bytes(); kind,_=mime(data)
        if hashlib.sha256(data).hexdigest()!=entry.get('hash'):
            raise OrganizationError('source_changed')
        for part,content_type,region in vision_parts(data,kind):
            encoded='data:'+content_type+';base64,'+base64.b64encode(part).decode('ascii')
            if len(encoded)>30*1024*1024:
                raise OrganizationError('image_too_large')
            if batch and (len(batch)==2 or size+len(encoded)>30*1024*1024):
                yield batch;batch=[];size=0
            item={'reference':entry['reference'],'data':encoded,'hash':hashlib.sha256(part).hexdigest()}
            if region is not None:
                item['region']=region
            batch.append(item);size+=len(encoded)
    if batch: yield batch


def input_label(item):
    suffix=' [原图分片坐标 '+','.join(map(str,item['region']))+']' if 'region' in item else ''
    return item['reference']+suffix
