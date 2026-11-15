"""Locked, short transactions; scanning and model calls stay outside them."""
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import select, func
from app.models import OrganizationControl, OrganizationItem, OrganizationJob, OrganizationCall, utcnow
from app.services.organization.contracts import OrganizationSettings, OrganizationError, fingerprint, policy
from app.services.organization.inventory import inspect_directory, sample_items


def defaults():
    return {'config':OrganizationSettings().model_dump(),'approved_policy':None,'sample_job_id':None,
            'initial_complete':False,'paused':False}


def item_view(item, detail=False):
    result={k:getattr(item,k) for k in ('id','identity','status','error','knowledge_id','export_path','created_at')}
    result.update(title=item.snapshot['values']['title'],body_chars=item.snapshot['body_chars'],
                  image_count=len(item.snapshot['images']),image_required=item.snapshot['text_chars']<200 and bool(item.snapshot['images']))
    if detail:
        result.update(result=item.result,original=item.snapshot['values'],input_hash=item.input_hash)
    return result


def job_view(job):
    return {k:getattr(job,k) for k in ('id','mode','status','selection','error','created_at','finished_at')}


class Store:
    def __init__(self,database,lock,root):
        self.database,self.lock,self.root=database,lock,Path(root)
        self.resolve_profile=None

    def approved(self,control):
        if control['approved_policy']!=policy(control['config']):return False
        expected=control.get('approved_profile_fingerprint')
        if expected is None:return True  # Legacy style approval; bound on recover/start.
        try:return self.resolve_profile(control['config']).fingerprint==expected
        except Exception:return False

    @contextmanager
    def transaction(self):
        with self.lock,self.database.session() as session:
            yield session
            session.commit()

    def control(self,session):
        record=session.get(OrganizationControl,1)
        return dict(record.value) if record else defaults()

    def set_control(self,session,value):
        row=session.get(OrganizationControl,1)
        if row:
            row.value=value
        else:
            session.add(OrganizationControl(id=1,value=value))

    def read(self):
        with self.transaction() as session:
            control=self.control(session)
            jobs=list(session.scalars(select(OrganizationJob).order_by(OrganizationJob.created_at.desc()).limit(20)))
            counts=dict(session.execute(select(OrganizationItem.status,func.count()).group_by(OrganizationItem.status)).all())
            costs=[{'period':period,'accounted_yuan':amount/1_000_000,'calls':count} for period,amount,count in session.execute(
                select(OrganizationCall.period,func.sum(OrganizationCall.accounted_micros),func.count()).group_by(OrganizationCall.period)).all()]
            for row in control.get('external_costs', []):
                total = next((value for value in costs if value['period'] == row['period']), None)
                if total is None:
                    total = {'period':row['period'], 'accounted_yuan':0, 'calls':0}; costs.append(total)
                total['accounted_yuan'] += row['accounted_micros']/1_000_000
                total['calls'] += row.get('calls',0)
            return {**control,'revision':fingerprint(control['config']),
                    'approved':self.approved(control),
                    'counts':counts,'budgets':costs,'jobs':[job_view(j) for j in jobs]}

    def output_directory(self):
        # Asset reads need one committed configuration value, not the scan lock
        # or the full control/jobs/cost projection used by the management page.
        with self.database.session() as session:
            row = session.get(OrganizationControl, 1)
            return row.value.get('config', {}).get('output_dir', '') if row else ''

    def require_idle(self,session):
        if session.scalar(select(OrganizationJob.id).where(OrganizationJob.status.in_(['pending','running'])).limit(1)):
            raise OrganizationError('organization_busy')

    def save(self,payload):
        config=OrganizationSettings.model_validate(payload.model_dump(exclude={'expected_revision'})).model_dump()
        for name in ('input_dir','output_dir'):
            if config[name]:
                path=Path(config[name]).resolve()
                for folder in ('data','knowledge','config','_internal','logs','backups'):
                    protected=(self.root/folder).resolve()
                    if path.is_relative_to(protected) or protected.is_relative_to(path):
                        raise OrganizationError('protected_directory')
        with self.transaction() as session:
            self.require_idle(session)
            current=self.control(session)
            if payload.expected_revision!=fingerprint(current['config']):
                raise OrganizationError('configuration_changed')
            if current['config']['input_dir'] and any(config[k]!=current['config'][k] for k in ('input_dir','output_dir')):
                if session.scalar(select(OrganizationItem.id).limit(1)):
                    raise OrganizationError('organization_paths_locked')
            if config['enabled'] and not self.approved({**current,'config':config}):
                raise OrganizationError('sample_approval_required')
            current['config']=config
            self.set_control(session,current)
        return self.read()

    def scan(self):
        config=self.read()['config']
        if not config['input_dir'] or not config['output_dir']:
            raise OrganizationError('configuration_incomplete')
        entries=inspect_directory(config['input_dir'])
        with self.transaction() as session:
            self.require_idle(session)
            existing={x.identity:x for x in session.scalars(select(OrganizationItem))}
            for entry in entries:
                old=existing.get(entry['identity'])
                if old is None:
                    session.add(OrganizationItem(identity=entry['identity'],snapshot=entry,input_hash=entry['input_hash']))
                elif old.input_hash!=entry['input_hash']:
                    old.error='source_changed'
                else:
                    old.snapshot={**old.snapshot,'relative_path':entry['relative_path'],'images':entry['images']}
            total=len(entries)
        return {'total':total,'long_articles':sum(x['body_chars']>20000 for x in entries),
                'image_articles':sum(x['text_chars']<200 and bool(x['images']) for x in entries)}

    def items(self,offset=0,limit=20,job_id=None,error=None):
        with self.transaction() as session:
            query=select(OrganizationItem)
            if error is not None:
                query=query.where(OrganizationItem.error==error)
            if job_id:
                job=session.get(OrganizationJob,job_id)
                if not job:
                    raise OrganizationError('job_not_found')
                query=query.where(OrganizationItem.id.in_(job.selection))
            total=session.scalar(select(func.count()).select_from(query.subquery()))
            rows=session.scalars(query.order_by(OrganizationItem.created_at,OrganizationItem.identity).offset(offset).limit(limit))
            return {'items':[item_view(x,True) for x in rows],'total':total,'offset':offset,'limit':limit}

    def approve_partial_image(self, identifier, input_hash):
        with self.transaction() as session:
            self.require_idle(session)
            control=self.control(session)
            if not self.approved(control):
                raise OrganizationError('sample_approval_required')
            item=session.get(OrganizationItem,identifier)
            if not item or item.error!='image_needs_review' or item.input_hash!=input_hash:
                raise OrganizationError('image_review_changed')
            item.snapshot={**item.snapshot,'partial_image_approval':{'input_hash':input_hash,'approved_at':utcnow()}}
            item.status='discovered';item.error=None;item.result=None
            return item_view(item,True)

    def start(self,mode):
        with self.transaction() as session:
            self.require_idle(session)
            if session.scalar(select(OrganizationJob.id).where(OrganizationJob.status=='paused').limit(1)):
                raise OrganizationError('paused_job_exists')
            control=self.control(session)
            config=control['config']
            if mode!='sample' and not self.approved(control):
                raise OrganizationError('sample_approval_required')
            if not(config['input_dir'] and config['output_dir']):
                raise OrganizationError('configuration_incomplete')
            rows=list(session.scalars(select(OrganizationItem).order_by(OrganizationItem.identity)))
            if mode=='sample':
                candidates=[{**x.snapshot,'item_id':x.id} for x in rows if x.status!='published' and not x.error]
                selected=[x['item_id'] for x in sample_items(candidates)]
            else:
                selected=[x.id for x in rows if x.status in (['failed'] if mode in {'retry','continue'} else ['discovered','ready'])
                          and (not x.error or mode in {'retry','continue'}) and x.error!='source_changed']
            if not selected:
                raise OrganizationError('no_pending_articles')
            for item in rows:
                if mode in {'retry','continue'} and item.id in selected:
                    item.status='discovered';item.error=None
            settings={**config,'retry':mode=='retry','initial_period':not control['initial_complete'],
                      'quality_enabled':control.get('quality_enabled',False)}
            if self.resolve_profile:
                from app.services.organization.providers import price_snapshot
                resolved=self.resolve_profile(config)
                settings.update(profile_fingerprint=resolved.fingerprint,price_snapshot=price_snapshot(resolved))
            job=OrganizationJob(mode=mode,selection=selected,settings=settings)
            session.add(job);session.flush()
            control['paused']=False
            if mode=='sample':
                control['sample_job_id']=job.id
            self.set_control(session,control)
            return job_view(job)

    def retry_sample(self,job_id,paid_retry=True):
        with self.transaction() as session:
            self.require_idle(session)
            control=self.control(session)
            job=session.get(OrganizationJob,job_id)
            if not job or job.mode!='sample' or job.status not in {'failed','completed_with_errors'}:
                raise OrganizationError('sample_not_failed')
            if policy({k:job.settings[k] for k in OrganizationSettings.model_fields})!=policy(control['config']):
                raise OrganizationError('configuration_changed')
            job.settings={**job.settings,'retry':paid_retry}
            job.status='pending';job.error=None;job.finished_at=None
            control['paused']=False;self.set_control(session,control)
            for identifier in job.selection:
                item=session.get(OrganizationItem,identifier)
                if item.error and item.error!='source_changed':
                    item.error=None;item.status='ready' if item.result else 'discovered'
        return self.read()

    def approve(self,job_id):
        with self.transaction() as session:
            self.require_idle(session)
            control=self.control(session)
            job=session.get(OrganizationJob,job_id)
            if (not job or job.mode!='sample' or job.status!='completed' or control['sample_job_id']!=job.id
                    or policy({k:job.settings[k] for k in OrganizationSettings.model_fields})!=policy(control['config'])
                    or any(session.get(OrganizationItem,x).status!='ready' for x in job.selection)):
                raise OrganizationError('sample_not_ready')
            control['approved_policy']=policy(control['config'])
            if self.resolve_profile:
                resolved=self.resolve_profile(control['config'])
                if job.settings.get('profile_fingerprint')!=resolved.fingerprint:
                    raise OrganizationError('organization_profile_changed')
                control['approved_profile_fingerprint']=resolved.fingerprint
            self.set_control(session,control)
        return self.read()

    def switch_profile(self,payload):
        with self.transaction() as session:
            self.require_idle(session)
            if session.scalar(select(OrganizationJob.id).where(OrganizationJob.status=='paused').limit(1)):
                raise OrganizationError('paused_job_exists')
            control=self.control(session);config=control['config']
            if payload.expected_revision!=fingerprint(config):
                raise OrganizationError('configuration_changed')
            if control['approved_policy']!=policy(config):
                raise OrganizationError('sample_approval_required')
            selected={**config,'profile_id':payload.profile_id}
            resolved=self.resolve_profile(selected)
            if resolved.fingerprint!=payload.expected_profile_fingerprint:
                raise OrganizationError('organization_profile_changed')
            history=list(control.get('profile_switches',[]))
            history.append({'from':config['profile_id'],'to':payload.profile_id,'at':utcnow(),
                            'from_fingerprint':control.get('approved_profile_fingerprint'),
                            'to_fingerprint':resolved.fingerprint,'model':resolved.profile.model})
            control.update(config=selected,approved_policy=policy(selected),
                           approved_profile_fingerprint=resolved.fingerprint,profile_switches=history)
            self.set_control(session,control)
            for item in session.scalars(select(OrganizationItem).where(OrganizationItem.status!='published')):
                if item.error!='source_changed':
                    item.result=None;item.error=None;item.status='discovered'
        return self.read()

    def pause(self):
        with self.transaction() as session:
            control=self.control(session);control['paused']=True;self.set_control(session,control)
            for job in session.scalars(select(OrganizationJob).where(OrganizationJob.status.in_(['pending','running']))):
                job.status='paused'
        return self.read()

    def resume(self,job_id):
        with self.transaction() as session:
            self.require_idle(session)
            job=session.get(OrganizationJob,job_id)
            control=self.control(session)
            if not job or job.status!='paused':
                raise OrganizationError('job_not_paused')
            if policy({k:job.settings[k] for k in OrganizationSettings.model_fields})!=policy(control['config']):
                raise OrganizationError('configuration_changed')
            job.status='pending';job.error=None
            control['paused']=False;self.set_control(session,control)
        return self.read()

    def cancel(self,job_id):
        with self.transaction() as session:
            self.require_idle(session)
            job=session.get(OrganizationJob,job_id)
            if not job or job.status!='paused':
                raise OrganizationError('job_not_paused')
            job.status='cancelled';job.finished_at=utcnow()
            control=self.control(session);control['paused']=True;self.set_control(session,control)
        return self.read()

    def recover(self):
        with self.transaction() as session:
            control=self.control(session)
            if self.resolve_profile and self.approved(control) and not control.get('approved_profile_fingerprint'):
                try:
                    control['approved_profile_fingerprint']=self.resolve_profile(control['config']).fingerprint
                    self.set_control(session,control)
                except Exception:pass
            for call in session.scalars(select(OrganizationCall).where(OrganizationCall.status=='reserved')):
                call.status='uncertain';call.error='interrupted_call'
            for job in session.scalars(select(OrganizationJob).where(OrganizationJob.status=='running')):
                job.status='pending'
