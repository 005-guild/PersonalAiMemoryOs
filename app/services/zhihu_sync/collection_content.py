"""Reuse full, accessible bodies already delivered for collection-page expansion."""

from bs4 import BeautifulSoup
from html import escape

from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.storage import SyncError
from app.services.zhihu_sync.export import image_url


def pin_body(content, identity):
    if normalize_zhihu_url(content['url']).canonical_url != identity.canonical_url:
        raise ValueError()
    parts = content['content']
    if not isinstance(parts, list) or not parts:
        raise ValueError()
    # Real collection responses can report image_count=0 with image parts present.
    # Preserve the full ordered parts; fold_content is only a preview.
    html = []
    for part in parts:
        if part['type'] == 'text':
            text = part['content']
            if not isinstance(text, str):
                raise ValueError()
            if not text.strip() and part.get('fold_content'):
                raise ValueError()
            html.append(text)
        elif part['type'] == 'image':
            url = image_url(part.get('original_url') or part['url'])
            html.append('<img src="' + escape(url, quote=True) + '">')
        else:
            raise ValueError()
    body = '\n'.join(html).strip()
    if not body:
        raise ValueError()
    title = content.get('excerpt_title') or BeautifulSoup(body, 'html.parser').get_text(' ', strip=True)
    if not isinstance(title, str):
        raise ValueError()
    return title.strip()[:100] or '知乎想法 ' + identity.external_id, body


def collection_body(content, identity):
    kind = identity.resource_type
    if kind not in {'answer', 'article', 'pin'}:
        return None
    try:
        if (content['type'] != kind or str(content['id']) != identity.external_id
                or content.get('is_deleted') is True or content.get('is_visible') is False):
            raise ValueError()
        if kind == 'pin':
            title, html = pin_body(content, identity)
            url = content['url']
        elif kind == 'answer':
            if (content.get('answer_type') != 'NORMAL' or content.get('is_normal') is not True
                    or content.get('is_collapsed') is True):
                raise ValueError()
            question = content['question']
            title = question['title']
            url = f"https://www.zhihu.com/question/{question['id']}/answer/{content['id']}"
        else:
            title, url = content['title'], content['url']
        if normalize_zhihu_url(url).canonical_url != identity.canonical_url:
            raise ValueError()
        if kind != 'pin':
            html = content['content']
        if not isinstance(title, str) or not title.strip() or not isinstance(html, str) or not html.strip():
            raise ValueError()
        soup = BeautifulSoup(html, 'html.parser')
        if soup.select('.PaidContent, .PurchaseButton'):
            raise ValueError()
        author = content.get('author', {}).get('name')
        if author is not None and not isinstance(author, str):
            raise ValueError()
        return {'title': title.strip(), 'author': author, 'html': html}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SyncError('source_incomplete') from None
