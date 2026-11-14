"""Explicit provider policies and immutable conservative CNY price snapshots."""
from urllib.parse import urlsplit
from app.agents.configuration import ResolvedProfile
from app.agents.errors import AIError
from app.services.organization.contracts import OrganizationError, fingerprint


def resolve(registry, config):
    try:active=registry.resolve(config['profile_id'])
    except AIError as error:raise OrganizationError(error.code) from None
    profile=active.profile
    url=urlsplit(profile.base_url)
    if url.scheme!='https' or url.port not in {None,443} or profile.auth not in {'auto','bearer'}:
        raise OrganizationError('organization_profile_unsupported')
    if (url.hostname=='api.deepseek.com' and url.path in {'','/v1'}
            and profile.protocol=='openai_chat' and profile.model=='deepseek-flash'):
        updates={'max_output_tokens':4096,'timeout_seconds':180.0,'response_format':'json_object',
                 'extra_body':{**profile.extra_body,'thinking':{'type':'disabled'}}}
    elif (url.hostname=='api.openai.com' and url.path=='/v1'
            and profile.protocol=='openai_responses' and profile.model=='gpt-6.1-sol'):
        if set(profile.extra_body)-{'reasoning','text','service_tier'}:
            raise OrganizationError('organization_profile_unsupported')
        updates={'max_output_tokens':8192,'timeout_seconds':180.0,'response_format':'json_object',
                 'extra_body':{**profile.extra_body,'reasoning':{'effort':'low'},'service_tier':'default'}}
    else:
        raise OrganizationError('organization_profile_unsupported')
    profile=profile.model_copy(update=updates)
    return ResolvedProfile(active.profile_id,profile,active.api_key,fingerprint(profile.model_dump()))


def price_snapshot(resolved):
    common={'version':1,'model':resolved.profile.model,'profile_fingerprint':resolved.fingerprint,
            'currency':'CNY','verified_on':'2026-11-14'}
    if resolved.profile.protocol=='openai_responses':
        # Input $2, cache writes up to $2.5, output $10 / MTok. Reserve and
        # account all input at the write rate; never assume a cache discount.
        return {**common,'provider':'openai','usd_to_cny':8,'input_micros':20,'output_micros':80,
                'long_input_threshold':272000,'long_input_multiplier':2,'long_output_multiplier':1.5}
    return {**common,'provider':'deepseek','input_micros':2,'output_micros':8}


def cost(prices, incoming, outgoing):
    long=incoming>prices.get('long_input_threshold',2_000_000)
    input_rate=prices['input_micros']*(prices.get('long_input_multiplier',1) if long else 1)
    output_rate=prices['output_micros']*(prices.get('long_output_multiplier',1) if long else 1)
    return incoming*int(input_rate)+outgoing*int(output_rate)


def describe(resolved):
    return {'id':resolved.profile_id,'model':resolved.profile.model,'fingerprint':resolved.fingerprint,
            'pricing':price_snapshot(resolved)}
