"""Reserve cost before HTTP; reuse received responses, never retry implicitly."""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from sqlalchemy import select,func
from app.models import OrganizationCall, OrganizationJob
from app.agents.configuration import ResolvedProfile
from app.agents.transport import _unique_keys, _invalid_constant
from app.services.organization.contracts import OrganizationError,fingerprint


class Calls:
    def __init__(self,store,registry,client,gate,stopping=lambda:False):
        self.store,self.registry,self.client,self.gate=store,registry,client,gate
        self.stopping=stopping

    def resolve(self,config):
        active=self.registry.resolve(config['profile_id'])
        if (active.profile.protocol!='openai_chat' or active.profile.model!='deepseek-flash'
                or urlsplit(active.profile.base_url).hostname!='api.deepseek.com'):
            raise OrganizationError('organization_profile_unsupported')
        body={**active.profile.extra_body,'thinking':{'type':'disabled'}}
        profile=active.profile.model_copy(update={'max_output_tokens':4096,'timeout_seconds':180.0,
                                                 'response_format':'json_object','extra_body':body})
        return ResolvedProfile(active.profile_id,profile,active.api_key,fingerprint(profile.model_dump()))

    async def generate(self,job_id,item_id,stage,system,user,validate,images=None):
        with self.store.transaction() as session:
            job=session.get(OrganizationJob,job_id);config=dict(job.settings)
        resolved=self.resolve(config)
        identity=fingerprint({'system':system,'user':user,'profile':resolved.fingerprint,'images':images or [],'stage':stage})
        with self.store.transaction() as session:
            job=session.get(OrganizationJob,job_id)
            if self.stopping() or job.status not in {'pending','running'} or self.store.control(session)['paused']:
                raise OrganizationError('organization_paused')
            if job.settings.get('profile_fingerprint') not in {None,resolved.fingerprint}:
                raise OrganizationError('organization_profile_changed')
            job.settings={**job.settings,'profile_fingerprint':resolved.fingerprint}
            previous=session.scalar(select(OrganizationCall).where(OrganizationCall.fingerprint==identity).order_by(OrganizationCall.attempt.desc()).limit(1))
            if previous and previous.status in {'received','succeeded'}:
                cached=(previous.id,previous.response)
            else:
                cached=None
                if previous and not config.get('retry'):
                    raise OrganizationError('explicit_retry_required')
        if cached:
            return self._validate(*cached,validate)
        # One shared generation slot also protects ordinary drafts and Q&A.
        while not self.gate.acquire(blocking=False):
            await asyncio.sleep(.1)
            with self.store.transaction() as session:
                if self.stopping() or session.get(OrganizationJob,job_id).status!='running':
                    raise OrganizationError('organization_paused')
        try:
            with self.store.transaction() as session:
                job=session.get(OrganizationJob,job_id)
                control=self.store.control(session)
                if self.stopping() or job.status!='running' or control['paused']:
                    raise OrganizationError('organization_paused')
                period='initial' if config['initial_period'] else datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m')
                budget=control['config']['initial_budget_yuan' if period=='initial' else 'monthly_budget_yuan']*1_000_000
                # UTF-8 byte count bounds text tokens conservatively; vision <=1024 tokens/image.
                reserve=(len((system+user).encode())+1024*len(images or [])+256)*2+4096*8
                used=session.scalar(select(func.coalesce(func.sum(OrganizationCall.accounted_micros),0)).where(OrganizationCall.period==period))
                if used+reserve>budget:
                    raise OrganizationError('organization_budget_exhausted')
                attempt=1+(previous.attempt if previous else 0)
                call=OrganizationCall(fingerprint=identity,attempt=attempt,job_id=job_id,item_id=item_id,
                    stage=stage,period=period,reserved_micros=reserve,accounted_micros=reserve)
                session.add(call);session.flush();identifier=call.id
            try:
                if images:
                    reply=await self.client.generate(resolved,system,user,images=images)
                else:
                    reply=await self.client.generate(resolved,system,user)
            except Exception as error:
                with self.store.transaction() as session:
                    call=session.get(OrganizationCall,identifier)
                    call.status='uncertain';call.error=getattr(error,'code','model_call_failed')
                raise OrganizationError(getattr(error,'code','model_call_failed')) from None
            with self.store.transaction() as session:
                call=session.get(OrganizationCall,identifier)
                call.response=reply.text;call.usage=reply.usage;call.status='received'
                incoming,outgoing=reply.usage.get('input_tokens'),reply.usage.get('output_tokens')
                if type(incoming) is int and type(outgoing) is int and incoming>=0 and outgoing>=0:
                    call.accounted_micros=incoming*2+outgoing*8
            return self._validate(identifier,reply.text,validate)
        finally:
            self.gate.release()

    def _validate(self,identifier,raw,validate):
        try:
            result=validate(json.loads(raw,object_pairs_hook=_unique_keys,parse_constant=_invalid_constant))
        except Exception:
            with self.store.transaction() as session:
                call=session.get(OrganizationCall,identifier);call.status='invalid';call.error='organization_output_invalid'
            raise OrganizationError('organization_output_invalid') from None
        with self.store.transaction() as session:
            session.get(OrganizationCall,identifier).status='succeeded'
        return result
