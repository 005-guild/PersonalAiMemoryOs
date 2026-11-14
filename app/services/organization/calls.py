"""Reserve cost before HTTP; reuse received responses, never retry implicitly."""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy import select,func
from app.models import OrganizationCall, OrganizationJob
from app.agents.transport import _unique_keys, _invalid_constant
from app.services.organization.contracts import OrganizationError,fingerprint
from app.services.organization import providers


class Calls:
    def __init__(self,store,registry,client,gate,stopping=lambda:False):
        self.store,self.registry,self.client,self.gate=store,registry,client,gate
        self.stopping=stopping

    def resolve(self,config):
        return providers.resolve(self.registry,config)

    async def generate(self,job_id,item_id,stage,system,user,validate,images=None,repair_system=None):
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
            prices=job.settings.get('price_snapshot') or providers.price_snapshot(resolved)
            job.settings={**job.settings,'profile_fingerprint':resolved.fingerprint,'price_snapshot':prices}
            previous=session.scalar(select(OrganizationCall).where(OrganizationCall.fingerprint==identity).order_by(OrganizationCall.attempt.desc()).limit(1))
            if previous and previous.status in {'received','succeeded','invalid'} and previous.response is not None:
                cached=(previous.id,previous.response,previous.status)
            else:
                cached=None
                if previous and not config.get('retry'):
                    raise OrganizationError('explicit_retry_required')
        if cached:
            try:
                return self._validate(cached[0],cached[1],validate)
            except OrganizationError:
                if repair_system:
                    repaired=system+'\n\n'+repair_system
                    repair_identity=fingerprint({'system':repaired,'user':user,'profile':resolved.fingerprint,'images':images or [],'stage':stage})
                    with self.store.transaction() as session:
                        saved=session.scalar(select(OrganizationCall.id).where(OrganizationCall.fingerprint==repair_identity).limit(1))
                    # Existing repair responses remain reusable even on unpaid continuation.
                    # Only an explicit retry can create a fresh corrected request.
                    if saved or config.get('retry'):
                        return await self.generate(job_id,item_id,stage,repaired,user,validate,images)
                if cached[2]!='invalid' or not config.get('retry'):
                    raise
        # One shared generation slot also protects ordinary drafts and Q&A.
        while not self.gate.acquire(blocking=False):
            await asyncio.sleep(.1)
            with self.store.transaction() as session:
                if self.stopping() or session.get(OrganizationJob,job_id).status!='running':
                    raise OrganizationError('organization_paused')
        try:
            incoming_bound=None
            if prices['provider']=='openai':
                try:
                    incoming_bound=await self.client.count_input_tokens(resolved,system,user,images=images)
                    if type(incoming_bound) is not int or not 0<=incoming_bound<=922000:
                        raise OrganizationError('invalid_token_count')
                except Exception as error:
                    raise OrganizationError(getattr(error,'code','organization_token_count_failed')) from None
            with self.store.transaction() as session:
                job=session.get(OrganizationJob,job_id)
                control=self.store.control(session)
                if self.stopping() or job.status!='running' or control['paused']:
                    raise OrganizationError('organization_paused')
                period='initial' if config['initial_period'] else datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m')
                budget=control['config']['initial_budget_yuan' if period=='initial' else 'monthly_budget_yuan']*1_000_000
                # Keep the historical DeepSeek reservation/cache behavior intact.
                bound=incoming_bound if incoming_bound is not None else len((system+user).encode())+1024*len(images or [])
                reserve=providers.cost(prices,bound+256,resolved.profile.max_output_tokens)
                used=session.scalar(select(func.coalesce(func.sum(OrganizationCall.accounted_micros),0)).where(OrganizationCall.period==period))
                if used+reserve>budget:
                    raise OrganizationError('organization_budget_exhausted')
                attempt=1+(previous.attempt if previous else 0)
                call=OrganizationCall(fingerprint=identity,attempt=attempt,job_id=job_id,item_id=item_id,
                    stage=stage,period=period,reserved_micros=reserve,accounted_micros=reserve,
                    price_snapshot={**prices,'estimated_input_tokens':bound})
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
                    call.accounted_micros=providers.cost(prices,incoming,outgoing)
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
