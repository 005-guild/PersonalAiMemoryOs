"""Manual, cacheable multi-article synthesis on the existing durable worker."""
import json
from sqlalchemy import select
from app.models import TopicSummary, OrganizationJob
from app.paths import resource_root
from app.repositories.topics import members, revision
from app.services.organization.contracts import OrganizationError
from app.services.topics.contracts import validate


class TopicService:
    def __init__(self,organization):
        self.organization=organization
        self.store=organization.store

    def view(self,topic):
        with self.store.database.session() as session:
            session.connection().exec_driver_sql('BEGIN')
            articles=members(session,topic)
            latest=session.scalar(select(TopicSummary).where(TopicSummary.topic==topic,TopicSummary.result.is_not(None))
                .order_by(TopicSummary.created_at.desc(),TopicSummary.id.desc()).limit(1))
            control=self.store.control(session)
            pending=session.scalar(select(TopicSummary).join(OrganizationJob).where(TopicSummary.topic==topic,
                OrganizationJob.status.in_(['pending','running','paused'])).order_by(TopicSummary.created_at.desc()).limit(1))
            estimated = None
            if articles and self.organization.calls.registry is not None:
                from app.services.organization.providers import cost,price_snapshot
                try:
                    resolved=self.organization.calls.resolve(control['config'])
                    requests=(len(articles)+11)//12; merges=0; count=requests
                    while count>1:
                        count=(count+5)//6;merges+=count
                    prices=price_snapshot(resolved)
                    estimated_cost=sum(cost(prices,len(json.dumps(articles[offset:offset+12],ensure_ascii=False).encode('utf-8'))//2+2048,2500)
                                       for offset in range(0,len(articles),12))
                    estimated_cost+=merges*cost(prices,6*2500+2048,2500)
                    estimated=estimated_cost/1_000_000
                except OrganizationError:
                    pass
            return {'topic':topic,'enabled':control.get('topics_enabled',False),'member_count':len(articles),
                'fingerprint':revision(articles),'result':latest.result if latest else None,
                'stale':bool(latest and latest.fingerprint!=revision(articles)),
                'members':[{'knowledge_id':row['knowledge_id'],'title':row['title']} for row in articles],
                'pending':{'id':pending.job_id,'status':session.get(OrganizationJob,pending.job_id).status} if pending else None,
                'monthly_budget_yuan':control['config']['monthly_budget_yuan'],'estimated_yuan':estimated}
            # Local estimates use expected output sizes; each actual request has its own counted reservation.

    def toggle(self,enabled):
        self.organization.writable()
        with self.store.transaction() as session:
            self.store.require_idle(session)
            control=self.store.control(session);control['topics_enabled']=enabled;self.store.set_control(session,control)
        return {'enabled':enabled}

    def start(self,topic,expected_fingerprint):
        self.organization.writable()
        with self.store.transaction() as session:
            self.store.require_idle(session)
            control=self.store.control(session)
            if not control.get('topics_enabled'):raise OrganizationError('topics_disabled')
            if control['paused']:raise OrganizationError('organization_paused')
            articles=members(session,topic)
            if not articles or topic=='待分类':raise OrganizationError('topic_members_missing')
            if expected_fingerprint!=revision(articles):raise OrganizationError('topic_members_changed')
            # Empty evidence would force the model to invent a basis. Keep the limitation visible.
            if any(not row['evidence'] for row in articles):raise OrganizationError('topic_evidence_missing')
            config=dict(control['config']);resolved=self.organization.calls.resolve(config)
            job=OrganizationJob(mode='topic',selection=[],settings={**config,'initial_period':False,
                'profile_fingerprint':resolved.fingerprint,'topic':topic})
            session.add(job);session.flush()
            record=TopicSummary(topic=topic,fingerprint=revision(articles),members=articles,job_id=job.id)
            session.add(record);session.flush();job.selection=[record.id]
            return {'id':job.id,'status':job.status}

    async def run(self,job_id):
        with self.store.transaction() as session:
            job=session.get(OrganizationJob,job_id);record=session.get(TopicSummary,job.selection[0])
            articles=list(record.members);topic=record.topic;record_id=record.id
        prompt=(resource_root()/'app/prompts/topic_summary_v1.md').read_text(encoding='utf-8')
        # Stable small groups bound context, allow exact cached continuation and retain all members.
        parts=[]
        for offset in range(0,len(articles),12):
            group=articles[offset:offset+12]
            value=await self.organization.calls.generate(job_id,None,'topic-group-v1',prompt,
                json.dumps({'topic':topic,'articles':group},ensure_ascii=False),lambda raw:validate(raw,group))
            parts.append(value)
        while len(parts)>1:
            merged=[]
            for offset in range(0,len(parts),6):
                group=parts[offset:offset+6]
                value=await self.organization.calls.generate(job_id,None,'topic-merge-v1',prompt,
                    json.dumps({'topic':topic,'group_summaries':group},ensure_ascii=False),lambda raw:validate(raw,articles))
                merged.append(value)
            parts=merged
        with self.store.transaction() as session:
            session.get(TopicSummary,record_id).result=parts[0]
