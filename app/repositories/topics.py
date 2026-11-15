"""Current topic members and grounded evidence from the collection's visible view."""
import json
from sqlalchemy import text
from app.repositories.collection_views import ELIGIBLE, INDEXED_FROM
from app.repositories.reading import TOPIC
from app.services.organization.contracts import fingerprint


def members(session,topic):
    rows=session.execute(text('SELECT k.id,k.version,k.title,k.summary,k.category,k.tags,o.input_hash,o.result,o.snapshot'
        +INDEXED_FROM+' WHERE '+ELIGIBLE+f' AND {TOPIC}=:topic ORDER BY k.id'),{'topic':topic}).mappings()
    result=[]
    for row in rows:
        organized=json.loads(row['result']) or {};snapshot=json.loads(row['snapshot'])
        original=snapshot['values']['content']
        quotes=(organized.get('detail') or {}).get('source_quotes') or [{'id':f'Q{i+1}','quote':quote} for i,quote in enumerate(organized.get('quotes',[]))]
        evidence=[{'id':quote['id'],'text':quote['quote'],'kind':'original'} for quote in quotes if quote['quote'] in original]
        evidence += [{'id':f'O{i+1}','text':observation['text'],'kind':'image_observation'}
                     for i,observation in enumerate(organized.get('image_observations',[])) if not observation.get('uncertain')]
        result.append({'knowledge_id':row['id'],'version':row['version'],'input_hash':row['input_hash'],
            'title':row['title'],'summary':row['summary'],'evidence':evidence})
    return result


def revision(articles):
    return fingerprint(articles)
