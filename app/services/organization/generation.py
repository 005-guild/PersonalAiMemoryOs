"""Grounded summaries, cached long-document steps, and bounded image inputs."""
import json
from pydantic import BaseModel, ConfigDict, Field
from app.paths import resource_root
from app.services.organization.contracts import OrganizationError,OrganizationSettings
from app.services.organization.inventory import chunks, IMAGE
from app.services.organization.evidence import visible_map,source_quote
from app.services.organization.images import image_inputs,input_label,mime


class Summary(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    title: str=Field(min_length=1,max_length=80)
    summary: str=Field(min_length=1,max_length=600)
    category: str=Field(min_length=1,max_length=80)
    tags: list[str]=Field(min_length=3,max_length=6)
    points: list[str]=Field(min_length=1,max_length=12)
    conditions: str=Field(max_length=600)
    quotes: list[str]=Field(max_length=3)


def prompt(name):
    return (resource_root()/f'app/prompts/collection_{name}_v1.md').read_text(encoding='utf-8')


def validate_quotes(values,body,required=True):
    if not isinstance(values,list) or len(values)>3 or (required and not values): raise ValueError()
    for quote in values:
        if not isinstance(quote,str) or not quote.strip() or len(quote)>200 or quote not in body: raise ValueError()


def grounded_quotes(values,body,required=True):
    """Discard unsupported/excess quotations, never rewrite or invent evidence."""
    if not isinstance(values,list) or len(values)>12 or any(not isinstance(x,str) for x in values):
        raise ValueError()
    kept=[]
    mapped=visible_map(body)
    for quote in values:
        literal=source_quote(quote,body,mapped)
        if literal and literal not in kept:
            kept.append(literal)
    kept=kept[:3]
    validate_quotes(kept,body,required)
    return kept


def summary_validator(snapshot,categories,visual=False):
    def validate(value):
        value={**value,'quotes':grounded_quotes(value['quotes'],snapshot['values']['content'],not visual)}
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
                json.dumps({'title':snapshot['values']['title'],'images':[input_label(x) for x in batch]},ensure_ascii=False),
                validate,images=[x['data'] for x in batch])
            if any(x['uncertain'] for x in values): raise OrganizationError('image_needs_review')
            observations += [{'image':batch[x['image']-1]['reference'],'text':x['text'],
                **({'region':batch[x['image']-1]['region']} if 'region' in batch[x['image']-1] else {})} for x in values]
    parts=[]
    if len(body)>20000:
        for index,part in enumerate(chunks(body)):
            def validate(value):
                if set(value)!={'summary','quotes'} or not isinstance(value['summary'],str) or not 1<=len(value['summary'])<=1200: raise ValueError()
                return {**value,'quotes':grounded_quotes(value['quotes'],part['content'])}
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
