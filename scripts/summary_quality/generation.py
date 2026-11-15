"""Strict evidence-bearing enhanced summaries; no publication or source mutation."""
import json
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.agents.configuration import ResolvedProfile
from app.agents.transport import _unique_keys,_invalid_constant
from app.services.organization.contracts import fingerprint
from app.services.organization.evidence import source_quote,visible_map
from app.services.organization.providers import resolve


from app.services.organization.quality_contract import Summary, validate, markdown


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
