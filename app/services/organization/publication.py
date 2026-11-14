"""Publish one Knowledge plus a conflict-checked categorized Markdown mirror."""
import hashlib
from pathlib import Path, PureWindowsPath
import re
from sqlalchemy import select,text
import yaml
from app.models import OrganizationItem,Knowledge
from app.services.importer import ImportService
from app.services.import_types import ParsedZhihuItem
from app.services.content import ContentService
from app.services.files import atomic_write,read_file,remove_file,FileChangedError
from app.services.organization.contracts import OrganizationError
from app.services.organization.images import mime,input_label
from app.services.organization.inventory import IMAGE
from app.services.zhihu_sync.storage import safe_path
from app.services.zhihu_sync.export import publish_file

ASSET_PREFIX='/api/v1/collection-organization/assets/'


def component(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]','',value).strip(' .')[:60].rstrip(' .') or '未命名'
    return '_'+name if PureWindowsPath(name).is_reserved() else name


def body(snapshot,result,original):
    lines=['## 总结',result['summary'],'','## 核心要点',*['- '+x for x in result['points']],
           '','## 适用条件与局限',result['conditions'] or '原文未明确说明。']
    if result.get('partial_image_summary'):
        lines=['> 部分图片文字无法辨认。本摘要经逐篇确认，仅依据清晰可辨内容，不代表截图全文。','',*lines]
    if result['quotes']:
        lines+=['','## 原文依据',*['> '+x.replace('\n','\n> ') for x in result['quotes']]]
    if result.get('image_observations'):
        lines+=['','## 图片读取记录（AI 识读）',*['- '+input_label({**x,'reference':x['image']})+
            ('：部分文字无法辨认，未用于摘要。' if x.get('uncertain') else '：'+x['text']) for x in result['image_observations']]]
    lines+=['','## 原文',f"原题：{snapshot['values']['title']}",f"来源：{snapshot['values']['url']}",'',original]
    return '\n'.join(lines)


class Publication:
    def __init__(self,store):
        self.store=store

    def assets(self,snapshot,config):
        root=safe_path(Path(config['input_dir']));output=safe_path(Path(config['output_dir']))
        replacements={}
        for asset in snapshot['images']:
            if asset.get('error'): raise OrganizationError(asset['error'])
            source=safe_path(root/asset['relative_path'])
            if not source.is_relative_to(root): raise OrganizationError('image_path_invalid')
            data=source.read_bytes()
            if hashlib.sha256(data).hexdigest()!=asset.get('hash'):
                raise OrganizationError('source_changed')
            if len(data)>20*1024*1024: raise OrganizationError('image_too_large')
            _,extension=mime(data)
            name=hashlib.sha256(data).hexdigest()+extension
            target=safe_path(output/'assets'/name)
            if not target.exists():
                publish_file(source,target)
            elif target.read_bytes()!=data:
                raise OrganizationError('asset_conflict')
            replacements[asset['reference']]=ASSET_PREFIX+name
        return IMAGE.sub(lambda m:m.group(0).replace(m[1],replacements[m[1]],1),snapshot['values']['content'])

    def publish(self,identifier,config):
        with self.store.transaction() as session:
            item=session.get(OrganizationItem,identifier);snapshot=dict(item.snapshot);result=item.result
            existing=item.knowledge_id
        if not result: raise OrganizationError('summary_missing')
        if not existing:
            original=self.assets(snapshot,config)
            parsed=ParsedZhihuItem(0,snapshot['resource_type'],snapshot['external_id'],snapshot['values'])
            imported=ImportService(self.store.database,self.store.lock).run([parsed]).items[0]
            if (not imported.source_id or imported.differing_fields
                    or imported.reason in {'deleted_source','legacy_deleted','ambiguous_legacy_match'}):
                raise OrganizationError('source_import_conflict')
            with self.store.transaction() as session:
                item=session.get(OrganizationItem,identifier)
                if not item.knowledge_id:
                    summary=('【部分图片文字无法辨认，仅总结清晰内容】\n' if result.get('partial_image_summary') else '')+result['summary']
                    note=ContentService(session).create_knowledge({'source_ids':[imported.source_id],
                        'title':result['title'],'summary':summary,'category':result['category'],
                        'tags':result['tags'],'concepts':[],'body':body(snapshot,result,original)})
                    item.source_id=imported.source_id;item.knowledge_id=note['id']
        self.export(identifier,config)

    def export(self,identifier,config):
        output=safe_path(Path(config['output_dir']));output.mkdir(parents=True,exist_ok=True)
        with self.store.transaction() as session:
            item=session.get(OrganizationItem,identifier);note=session.get(Knowledge,item.knowledge_id)
            if not note or note.deleted_at: raise OrganizationError('organized_note_deleted')
            snapshot=dict(item.snapshot)
            category=note.category or '待分类/待确认'
            pieces=category.split('/')
            if len(pieces)!=2: pieces=['待分类',category]
            relative='/'.join([*[component(x) for x in pieces],component(note.title)+'--'+item.identity.replace(':','-')+'.md'])
            metadata={'knowledge_id':note.id,'title':note.title,'original_title':snapshot['values']['title'],
                'author':snapshot['values'].get('author'),'source':snapshot['values']['url'],
                'zhihu_id':snapshot['external_id'],'type':snapshot['resource_type'],'category':category,'tags':note.tags}
            if item.result.get('partial_image_summary'):
                metadata['partial_image_summary']=True
                metadata['image_review']=snapshot.get('partial_image_approval')
            content='---\n'+yaml.safe_dump(metadata,allow_unicode=True,sort_keys=False)+'---\n'+note.body.replace(ASSET_PREFIX,'../../assets/')
            wanted=hashlib.sha256(content.encode()).hexdigest()
            try:
                if item.export_path and item.export_path!=relative:
                    previous=read_file(output,item.export_path)
                    if previous and previous.hash!=item.export_hash: raise FileChangedError('edited')
                current=read_file(output,relative)
                if not current or current.hash!=wanted:
                    expected=item.export_hash if item.export_path==relative and current else None
                    atomic_write(output,relative,content,expected)
                if item.export_path and item.export_path!=relative and read_file(output,item.export_path):
                    remove_file(output,item.export_path,item.export_hash)
            except FileChangedError:
                raise OrganizationError('export_conflict') from None
            item.export_path=relative;item.export_hash=wanted;item.exported_version=note.version;item.status='published';item.error=None
            session.execute(text('DELETE FROM organization_fts WHERE item_id=:id'),{'id':identifier})
            session.execute(text('INSERT INTO organization_fts(item_id,title,summary,original,tags) VALUES(:id,:title,:summary,:original,:tags)'),
                {'id':identifier,'title':note.title+' '+snapshot['values']['title'],'summary':note.summary,
                 'original':note.body,'tags':' '.join(note.tags)})

    def refresh(self,config):
        with self.store.transaction() as session:
            identifiers=list(session.scalars(select(OrganizationItem.id).join(Knowledge,OrganizationItem.knowledge_id==Knowledge.id)
                .where(OrganizationItem.status=='published',OrganizationItem.error.is_(None),
                       Knowledge.deleted_at.is_(None))))
        for identifier in identifiers:
            try: self.export(identifier,config)
            except Exception:
                with self.store.transaction() as session:
                    item=session.get(OrganizationItem,identifier)
                    item.error='export_conflict';item.status='failed'
