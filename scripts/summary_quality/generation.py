"""Strict evidence-bearing enhanced summaries; no publication or source mutation."""
import json
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.agents.configuration import ResolvedProfile
from app.agents.transport import _unique_keys,_invalid_constant
from app.services.organization.contracts import fingerprint
from app.services.organization.evidence import source_quote,visible_map
from app.services.organization.providers import resolve


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)

    @field_validator('*')
    @classmethod
    def visible(cls,value):
        if isinstance(value,str) and not value.strip(): raise ValueError('blank')
        return value


class Quote(Strict):
    id: str = Field(pattern=r'^Q[1-6]$')
    quote: str = Field(min_length=1,max_length=400)


class Point(Strict):
    heading: str = Field(min_length=1,max_length=100)
    detail: str = Field(min_length=1,max_length=3000)
    evidence_ids: list[str] = Field(min_length=1,max_length=20)


class Summary(Strict):
    summary: str = Field(min_length=1,max_length=600)
    overview: str = Field(min_length=1,max_length=2000)
    points: list[Point] = Field(min_length=1,max_length=10)
    conditions: str = Field(min_length=1,max_length=2000)
    conclusion: str = Field(min_length=1,max_length=1500)
    source_quotes: list[Quote] = Field(max_length=6)
    image_evidence_ids: list[str] = Field(max_length=100)


def pilot_profile(registry):
    resolved = resolve(registry,{'profile_id':registry.default_profile})
    if resolved.profile.protocol != 'openai_responses': raise RuntimeError('pilot_requires_configured_openai_default')
    profile = resolved.profile.model_copy(update={'max_output_tokens':4096})
    return ResolvedProfile(resolved.profile_id,profile,resolved.api_key,fingerprint(profile.model_dump()))


def user_input(sample):
    if sample['prepare_error']: raise RuntimeError(sample['prepare_error'])
    return json.dumps({'title':sample['original']['title'],'author':sample['original'].get('author'),
        'content':sample['original']['content'],'clear_image_observations':sample['observations'],
        'partial_image_input':sample['partial']},ensure_ascii=False)


def validate(raw,sample):
    value = Summary.model_validate(json.loads(raw,object_pairs_hook=_unique_keys,parse_constant=_invalid_constant)).model_dump()
    original = sample['original']['content'];mapped = visible_map(original)
    ids = [quote['id'] for quote in value['source_quotes']]
    if len(set(ids)) != len(ids): raise ValueError('duplicate_quote')
    for quote in value['source_quotes']:
        literal = source_quote(quote['quote'],original,mapped)
        if not literal: raise ValueError('unsupported_quote')
        quote['quote'] = literal
    clear = {row['id'] for row in sample['observations']}
    used = set(value['image_evidence_ids'])
    if not used <= clear or len(used) != len(value['image_evidence_ids']): raise ValueError('unsupported_image_evidence')
    if sample['image_only']:
        # Image-heavy posts may still have a literal text caption. The quote
        # checks above verify it against the actual text, never OCR prose.
        if not used and not ids: raise ValueError('image_evidence_required')
    elif not ids: raise ValueError('source_quote_required')
    for point in value['points']:
        if not set(point['evidence_ids']) <= set(ids)|used: raise ValueError('unsupported_point_evidence')
    if sample['partial'] and any('部分图片文字无法辨认' not in value[key] for key in ('summary','overview','conditions')):
        raise ValueError('partial_warning_missing')
    return value


def markdown(value):
    parts = ['## 短提要',value['summary'],'','## 文章概述',value['overview'],'','## 主要内容']
    for point in value['points']:
        parts += ['','### '+point['heading'],point['detail'],'依据：'+ '、'.join(point['evidence_ids'])]
    parts += ['','## 条件与局限',value['conditions'],'','## 作者结论',value['conclusion'],'','## 原文依据']
    parts += [f"- {quote['id']}：{quote['quote']}" for quote in value['source_quotes']]
    if value['image_evidence_ids']: parts += ['图片识读依据（非逐字原文）：'+ '、'.join(value['image_evidence_ids'])]
    return '\n'.join(parts)
