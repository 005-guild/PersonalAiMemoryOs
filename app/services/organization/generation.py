"""Grounded summaries, cached long-document steps, and bounded image inputs."""
import base64
import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from app.paths import resource_root
from app.services.organization.contracts import OrganizationError,OrganizationSettings
from app.services.organization.inventory import chunks, IMAGE
from app.services.zhihu_sync.storage import safe_path


class Summary(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    title: str=Field(min_length=1,max_length=80)
    summary: str=Field(min_length=1,max_length=600)
    category: str=Field(min_length=1,max_length=80)
    tags: list[str]=Field(min_length=3,max_length=6)
    points: list[str]=Field(min_length=1,max_length=8)
    conditions: str=Field(max_length=600)
    quotes: list[str]=Field(max_length=3)


def prompt(name):
    return (resource_root()/f'app/prompts/collection_{name}_v1.md').read_text(encoding='utf-8')


def mime(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png','.png'
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg','.jpg'
    if data.startswith((b'GIF87a',b'GIF89a')): return 'image/gif','.gif'
    if data.startswith(b'RIFF') and data[8:12]==b'WEBP': return 'image/webp','.webp'
    raise OrganizationError('image_format_unsupported')


def image_inputs(snapshot,directory):
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
        encoded='data:'+kind+';base64,'+base64.b64encode(data).decode('ascii')
        if batch and (len(batch)==2 or size+len(encoded)>30*1024*1024):
            yield batch;batch=[];size=0
        batch.append({'reference':entry['reference'],'data':encoded,'hash':hashlib.sha256(data).hexdigest()});size+=len(encoded)
    if batch: yield batch


def validate_quotes(values,body,required=True):
    if not isinstance(values,list) or len(values)>3 or (required and not values): raise ValueError()
    for quote in values:
        if not isinstance(quote,str) or not quote.strip() or len(quote)>200 or quote not in body: raise ValueError()


def summary_validator(snapshot,categories,visual=False):
    def validate(value):
        result=Summary.model_validate(value).model_dump()
        if result['category'] not in categories: raise ValueError()
        for field in ('tags','points'):
            if len(set(result[field]))!=len(result[field]) or any(not x.strip() or len(x)>400 for x in result[field]): raise ValueError()
        validate_quotes(result['quotes'],snapshot['values']['content'],not visual)
        return result
    return validate


async def taxonomy(calls,store,job_id,entries):
    def validate(value):
        if set(value)!={'categories'}: raise ValueError()
        categories=value['categories']
        OrganizationSettings(taxonomy=categories)
        if not 8<=len({x.split('/')[0] for x in categories})<=12 or '待分类/待确认' not in categories: raise ValueError()
        return categories
    value=await calls.generate(job_id,None,'taxonomy',prompt('taxonomy'),json.dumps(
        {'titles':[x['values']['title'][:120] for x in entries]},ensure_ascii=False),validate)
    from app.models import OrganizationJob
    with store.transaction() as session:
        job=session.get(OrganizationJob,job_id)
        job.settings={**job.settings,'taxonomy':value}
        control=store.control(session);control['config']={**control['config'],'taxonomy':value};store.set_control(session,control)
    return value


async def summarize(calls,job_id,item_id,snapshot,config):
    original=snapshot['values']['content'];body=original
    observations=[]
    if snapshot['text_chars']<200 and snapshot['images']:
        for index,batch in enumerate(image_inputs(snapshot,config['input_dir'])):
            def validate(value):
                rows=value['observations']
                if len(rows)!=len(batch): raise ValueError()
                for number,row in enumerate(rows,1):
                    if set(row)!={'image','text','uncertain'} or row['image']!=number or type(row['uncertain']) is not bool or not isinstance(row['text'],str) or not row['text'].strip() or len(row['text'])>1500: raise ValueError()
                return rows
            values=await calls.generate(job_id,item_id,f'vision-{index}',prompt('vision'),
                json.dumps({'title':snapshot['values']['title'],'images':[x['reference'] for x in batch]},ensure_ascii=False),
                validate,images=[x['data'] for x in batch])
            if any(x['uncertain'] for x in values): raise OrganizationError('image_needs_review')
            observations += [{'image':batch[x['image']-1]['reference'],'text':x['text']} for x in values]
    parts=[]
    if len(body)>20000:
        for index,part in enumerate(chunks(body)):
            def validate(value):
                if set(value)!={'summary','quotes'} or not isinstance(value['summary'],str) or not 1<=len(value['summary'])<=800: raise ValueError()
                validate_quotes(value['quotes'],part['content'])
                return value
            extracted=await calls.generate(job_id,item_id,f'chunk-{index}',prompt('chunk'),
                json.dumps({'title':snapshot['values']['title'],**part},ensure_ascii=False),validate)
            parts.append({**extracted,'start':part['start'],'end':part['end']})
        body=''
    value={'title':snapshot['values']['title'],'author':snapshot['values'].get('author'),'content':body,
           'parts':parts,'image_observations':observations,'categories':config['taxonomy']}
    result=await calls.generate(job_id,item_id,'summary',prompt('summary'),json.dumps(value,ensure_ascii=False),
        summary_validator(snapshot,config['taxonomy'],bool(observations)))
    result['image_observations']=observations
    return result
