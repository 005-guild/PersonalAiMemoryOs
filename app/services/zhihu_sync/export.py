"""Convert one complete source body and publish new files without overwriting."""

import hashlib
import os
from pathlib import Path
import re
from uuid import uuid4
from urllib.parse import urlsplit, urljoin

from bs4 import BeautifulSoup
from markdownify import markdownify
import yaml

from app.services.zhihu_parser import ZhihuInputItem
from app.services.zhihu_sync.storage import SyncError, atomic_json, read_json, safe_path, identity_key


def image_url(value: str) -> str:
    value = urljoin('https://www.zhihu.com/', value)
    parsed = urlsplit(value)
    if (parsed.scheme not in {'https', 'http'} or parsed.username or parsed.password
            or parsed.port is not None or not parsed.hostname
            or not (parsed.hostname == 'zhimg.com' or parsed.hostname.endswith('.zhimg.com')
                    or (parsed.hostname == 'www.zhihu.com' and parsed.path == '/equation'))):
        raise SyncError('image_host_unsupported')
    return value.replace('http://', 'https://', 1)


def filename(title: str, identity) -> str:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title).strip(' .')[:70].rstrip(' .')
    return f'{title or "知乎"}--{identity.resource_type}-{identity.external_id}.md'


def render(identity, title: str, author: str | None, html: str, downloaded: str):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.select('script, style, iframe, button, noscript'):
        tag.decompose()
    assets = []
    urls = {}
    for image in soup.find_all('img'):
        formula = image.get('data-tex')
        if formula:
            image.replace_with(f'${formula}$')
            continue
        url = image_url(image.get('data-original') or image.get('data-actualsrc') or image.get('src') or '')
        if url not in urls:
            suffix = Path(urlsplit(url).path).suffix.lower()
            if suffix not in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'}:
                suffix = '.jpg'
            name = f'{identity.resource_type}-{identity.external_id}-{hashlib.sha256(url.encode()).hexdigest()[:16]}{suffix}'
            urls[url] = 'images/' + name
            assets.append({'url':url, 'path':urls[url]})
        image['src'] = urls[url]
    for link in soup.find_all('a', href=True):
        href = urljoin(identity.canonical_url, link['href'])
        if urlsplit(href).scheme in {'http', 'https', 'mailto'}:
            link['href'] = href
        else:
            del link['href']
    body = markdownify(str(soup), heading_style='ATX', bullets='-', code_language_callback=lambda el: el.get('data-language', ''))
    # Reuse the import contract before creating any final file.
    ZhihuInputItem.model_validate({'url':identity.canonical_url, 'title':title, 'author':author, 'content':body})
    meta = {'id':identity.external_id, 'title':title, 'author':author,
            'type':'zhihu-' + identity.resource_type, 'source':identity.canonical_url, 'downloaded':downloaded}
    content = '---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + '---\n' + body.rstrip() + '\n'
    return {'key':identity_key(identity), 'filename':filename(title, identity), 'content':content, 'assets':assets}


def publish_file(source: Path, target: Path):
    """Atomically publish a separate copy; never retain a writable alias to the final file."""
    source, target = safe_path(source), safe_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = safe_path(target.with_name('.zhihu-' + uuid4().hex + '.tmp'))
    try:
        with temporary.open('xb') as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if source.read_bytes() != target.read_bytes():
                raise SyncError('output_conflict') from None
    finally:
        temporary.unlink(missing_ok=True)


class Exporter:
    def __init__(self, ledger):
        self.ledger = ledger

    def staged(self, identity):
        directory = safe_path(self.ledger.directory / 'pending' / identity_key(identity).replace(':', '-'))
        document = directory / 'document.json'
        if not document.exists():
            return None
        payload = read_json(document)
        try:
            if (payload['key'] != identity_key(identity)
                    or Path(payload['filename']).name != payload['filename']
                    or not payload['filename'].endswith('.md') or not isinstance(payload['content'], str)):
                raise ValueError()
            for asset in payload['assets']:
                if not re.fullmatch(r'images/[a-z]+-[0-9]+-[0-9a-f]{16}\.[a-z]+', asset['path']):
                    raise ValueError()
                image_url(asset['url'])
        except (KeyError, TypeError, ValueError):
            raise SyncError('pending_invalid') from None
        return payload

    def finish(self, identity, payload, fetch_image, stopping):
        directory = safe_path(self.ledger.directory / 'pending' / identity_key(identity).replace(':', '-'))
        atomic_json(directory / 'document.json', payload)
        for asset in payload['assets']:
            if stopping():
                raise SyncError('cancelled')
            staged = safe_path(directory / Path(asset['path']).name)
            if not staged.exists():
                data = fetch_image(asset['url'])
                if not data or len(data) > 20 * 1024 * 1024:
                    raise SyncError('image_invalid')
                temporary = safe_path(staged.with_suffix('.part'))
                with temporary.open('wb') as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, staged)
            publish_file(staged, self.ledger.target / asset['path'])
        markdown = safe_path(directory / 'article.md')
        with markdown.open('w', encoding='utf-8', newline='\n') as handle:
            handle.write(payload['content'])
            handle.flush()
            os.fsync(handle.fileno())
        publish_file(markdown, self.ledger.target / payload['filename'])
        self.ledger.complete(identity, payload['filename'])
        # Completion is durable before cleaning only this export's known staging files.
        for name in ['article.md', 'document.json', *[Path(item['path']).name for item in payload['assets']]]:
            try:
                safe_path(directory / name).unlink(missing_ok=True)
            except OSError:
                pass
