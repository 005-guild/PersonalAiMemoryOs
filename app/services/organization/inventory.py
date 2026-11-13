"""Read originals without changing their bytes or existing sync ledger."""
from pathlib import Path
import hashlib
import re
from urllib.parse import unquote, urlsplit
from app.services.import_types import ParsedZhihuItem
from app.services.zhihu_markdown import _entry
from app.services.zhihu_sync.storage import safe_path
from app.services.organization.contracts import OrganizationError, fingerprint

IMAGE = re.compile(r'!\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)')


def inspect_directory(directory):
    root=safe_path(Path(directory))
    if not root.is_dir():
        raise OrganizationError('input_directory_missing')
    seen, identities, entries = set(), set(), []
    for index,path in enumerate(sorted(root.glob('*.md'))):
        if path.name.casefold()=='readme.md':
            continue
        if path.stat().st_size>10*1024*1024:
            raise OrganizationError('source_too_large')
        parsed,_=_entry(index,{'relative_path':path.name,'content':safe_path(path).read_text(encoding='utf-8-sig')},seen)
        if not isinstance(parsed,ParsedZhihuItem):
            raise OrganizationError('source_invalid')
        identity=parsed.resource_type+':'+parsed.external_id
        if identity in identities:
            raise OrganizationError('duplicate_source_identity')
        identities.add(identity)
        body=parsed.values['content']
        images=[]
        for match in IMAGE.finditer(body):
            relative=unquote(match[1])
            if urlsplit(relative).scheme or relative.startswith(('/', '\\')):
                images.append({'reference':match[1], 'error':'image_not_local'})
                continue
            candidate=safe_path(root/relative)
            if not candidate.is_relative_to(root) or not candidate.is_file():
                images.append({'reference':match[1], 'error':'image_missing'})
                continue
            if candidate.stat().st_size>20*1024*1024:
                images.append({'reference':match[1], 'error':'image_too_large'})
                continue
            images.append({'reference':match[1], 'relative_path':candidate.relative_to(root).as_posix(),
                           'hash':hashlib.sha256(candidate.read_bytes()).hexdigest()})
        text=IMAGE.sub('',body)
        entries.append({'identity':identity,'resource_type':parsed.resource_type,'external_id':parsed.external_id,
            'relative_path':path.name, 'values':parsed.values,'input_hash':fingerprint({'values':parsed.values,'images':images}),
            'images':images,'text_chars':len(re.sub(r'\s+','',text)), 'body_chars':len(body)})
    return entries


def sample_items(entries):
    ordered=sorted(entries,key=lambda x:x['identity'])
    visual=[x for x in ordered if x['text_chars']<200 and x['images']][:2]
    long=sorted((x for x in ordered if x['body_chars']>20000 and x not in visual),key=lambda x:-x['body_chars'])[:2]
    chosen=visual+long
    chosen += [x for x in ordered if x not in chosen and x['body_chars']<=20000 and x['text_chars']>=200][:10-len(chosen)]
    chosen += [x for x in ordered if x not in chosen][:10-len(chosen)]
    return chosen


def chunks(body, limit=12000, overlap=200):
    start=0
    while start<len(body):
        end=min(start+limit,len(body))
        if end<len(body):
            boundary=body.rfind('\n',start+limit//2,end)
            if boundary>start:
                end=boundary+1
        yield {'start':start,'end':end,'content':body[start:end]}
        if end==len(body):
            break
        start=end-overlap
