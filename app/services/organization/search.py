"""SQLite trigram and short Chinese query search over generated notes and originals."""
import json
from sqlalchemy import text,select
from app.models import OrganizationItem,Knowledge,SyncState


def keyword_search(store,query,category='',tag='',limit=20,offset=0):
    query=query.strip()
    with store.transaction() as session:
        params={'limit':limit,'offset':offset,'category':category,'tag':tag}
        where="o.status='published' AND o.error IS NULL AND o.exported_version=k.version AND k.deleted_at IS NULL AND (s.status IS NULL OR s.status NOT IN ('conflict','error'))"
        where+=" AND (:category='' OR k.category=:category) AND (:tag='' OR EXISTS(SELECT 1 FROM json_each(k.tags) WHERE value=:tag))"
        if len(query)>=3:
            params['match']='"'+query.replace('"','""')+'"'
            where+=' AND organization_fts MATCH :match'
            order='bm25(organization_fts,0,5,3,1,2)'
        elif query:
            params['q']='%'+query.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
            where+=" AND (organization_fts.title LIKE :q ESCAPE '!' OR organization_fts.summary LIKE :q ESCAPE '!' OR organization_fts.original LIKE :q ESCAPE '!' OR organization_fts.tags LIKE :q ESCAPE '!')"
            order='k.updated_at DESC'
        else: order='k.updated_at DESC'
        # Keep the FTS scan outermost: escaped short LIKE queries have no trigram
        # constraint, so a reordered join would rescan all text for every item.
        base=' FROM organization_fts CROSS JOIN organization_items o ON o.id=organization_fts.item_id CROSS JOIN knowledge k ON k.id=o.knowledge_id LEFT JOIN sync_states s ON s.knowledge_id=k.id WHERE '+where
        total=session.scalar(text('SELECT count(*)'+base),params)
        rows=session.execute(text('SELECT o.id,k.id AS knowledge_id,k.title,k.summary,k.category,k.tags,k.body,o.snapshot'+base+' ORDER BY '+order+' LIMIT :limit OFFSET :offset'),params).mappings()
        items=[]
        for row in rows:
            source=json.loads(row['snapshot'])['values']
            hit='summary' if not query or query in row['summary'] or query in row['title'] else 'original'
            content=row['summary'] if hit=='summary' else row['body']
            index=max(0,content.find(query)-60) if query else 0
            items.append({'id':row['id'],'knowledge_id':row['knowledge_id'],'title':row['title'],'summary':row['summary'],
                'category':row['category'],'tags':json.loads(row['tags']),'match_section':hit,'excerpt':content[index:index+260],
                'source_title':source['title'],'source_url':source['url']})
        return {'items':items,'total':total,'offset':offset,'limit':limit}


async def semantic_search(store,retrieval,query,category='',tag=''):
    with store.transaction() as session:
        rows=session.execute(select(OrganizationItem,Knowledge).join(Knowledge,OrganizationItem.knowledge_id==Knowledge.id)
                             .where(OrganizationItem.status=='published',OrganizationItem.error.is_(None),Knowledge.deleted_at.is_(None))).all()
        identities={note.id for item,note in rows if (not category or note.category==category) and (not tag or tag in note.tags)}
    if not identities:
        return {'items':[],'total':0,'index_incomplete':False}
    result=await retrieval.retrieve(query,10,knowledge_ids=identities)
    with store.transaction() as session:
        items=[]
        for hit in result['notes']:
            item=session.scalar(select(OrganizationItem).where(OrganizationItem.knowledge_id==hit['knowledge_id']))
            if not item: continue
            note=session.get(Knowledge,item.knowledge_id)
            if (category and note.category!=category) or (tag and tag not in note.tags): continue
            items.append({'id':item.id,'knowledge_id':note.id,'title':note.title,'summary':note.summary,
                'category':note.category,'tags':note.tags,'match_section':'semantic','excerpt':note.summary,
                'source_title':item.snapshot['values']['title'],'source_url':item.snapshot['values']['url']})
    return {'items':items,'total':len(items),'index_incomplete':result['index_incomplete']}
