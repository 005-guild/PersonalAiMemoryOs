"""Reuse full, accessible bodies already delivered for collection-page expansion."""

from bs4 import BeautifulSoup

from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.storage import SyncError


def collection_body(content, identity):
    kind = identity.resource_type
    if kind not in {'answer', 'article'}:
        return None
    try:
        if (content['type'] != kind or str(content['id']) != identity.external_id
                or content.get('is_deleted') is True or content.get('is_visible') is False):
            raise ValueError()
        if kind == 'answer':
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
