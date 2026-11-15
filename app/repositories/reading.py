"""Read-only, bounded projections over the existing collection full-text index."""

import json
from collections import Counter
from sqlalchemy import select, text
from app.models import Knowledge, OrganizationItem
from app.repositories.collection_views import ELIGIBLE, INDEXED_FROM, keyword_condition

CATEGORY = "coalesce(nullif(k.category,''),'未分类')"
TOPIC = f"CASE WHEN instr({CATEGORY},'/')>0 THEN substr({CATEGORY},1,instr({CATEGORY},'/')-1) ELSE {CATEGORY} END"
MONTH = "strftime('%Y-%m',k.updated_at,'+8 hours')"
BASE = INDEXED_FROM + ' WHERE ' + ELIGIBLE
SOURCE_TITLE = "coalesce(json_extract(o.snapshot,'$.values.title'),'')"


class ReadingRepository:
    def __init__(self, session):
        self.session = session

    def overview(self):
        rows = self.session.execute(text(f'SELECT {CATEGORY} category,k.tags,{MONTH} month' + BASE)).mappings()
        categories, topics, tags, months = Counter(), Counter(), Counter(), Counter()
        total = 0
        for row in rows:
            total += 1
            categories[row['category']] += 1
            topics[row['category'].split('/', 1)[0]] += 1
            tags.update(set(json.loads(row['tags'])))
            if row['month']:
                months[row['month']] += 1
        all_items = self.session.scalar(text('SELECT count(*) FROM organization_items o '
            'LEFT JOIN knowledge k ON k.id=o.knowledge_id WHERE k.deleted_at IS NULL'))
        counts = lambda values: [{'name': name, 'count': count} for name, count in
                                 sorted(values.items(), key=lambda x: (-x[1], x[0]))]
        return {'total': total, 'unavailable_count': max(0, all_items - total),
                'topics': counts(topics), 'categories': [dict(x, topic=x['name'].split('/', 1)[0]) for x in counts(categories)],
                'tags': counts(tags), 'months': sorted(months, reverse=True),
                'recent': self.notes(limit=12)['items']}

    def notes(self, *, q='', topic='', category='', tag='', updated_month='', sort='updated_desc', offset=0, limit=20):
        query = q.strip()
        params = {'needle': query, 'topic': topic, 'category': category, 'tag': tag,
                  'month': updated_month, 'offset': offset, 'limit': limit}
        where = (f" AND (:topic='' OR {TOPIC}=:topic) AND (:category='' OR {CATEGORY}=:category)"
                 " AND (:tag='' OR EXISTS(SELECT 1 FROM json_each(k.tags) WHERE value=:tag))"
                 f" AND (:month='' OR {MONTH}=:month)") + keyword_condition(query, params)
        base = BASE + where
        total = self.session.scalar(text('SELECT count(*)' + base), params)
        order = 'k.title COLLATE NOCASE,k.id' if sort == 'title_asc' else 'k.updated_at DESC,k.id DESC'
        # Only the selected page receives excerpts. Never transfer complete bodies/snapshots to lists.
        hit = (f"CASE WHEN :needle='' OR instr(lower(k.title||' '||{SOURCE_TITLE}),lower(:needle))>0 THEN 'title' "
               "WHEN instr(lower(k.summary),lower(:needle))>0 THEN 'summary' "
               "WHEN instr(lower(k.tags),lower(:needle))>0 THEN 'tag' ELSE 'original' END")
        excerpt = ("CASE WHEN :needle='' OR instr(lower(k.summary),lower(:needle))>0 "
                   "THEN substr(k.summary,max(1,instr(lower(k.summary),lower(:needle))-60),260) "
                   "ELSE substr(k.body,max(1,instr(lower(k.body),lower(:needle))-60),260) END")
        columns = (f'SELECT k.id knowledge_id,k.title,substr(k.summary,1,600) summary,{CATEGORY} category,k.tags,'
                   f'k.updated_at,k.version,{SOURCE_TITLE} source_title,'
                   "json_extract(o.snapshot,'$.values.author') author,json_extract(o.snapshot,'$.values.url') source_url,"
                   f'{hit} match_section,{excerpt} excerpt')
        rows = self.session.execute(text(columns + base + ' ORDER BY ' + order + ' LIMIT :limit OFFSET :offset'), params).mappings()
        return {'items': [dict(row, tags=json.loads(row['tags'])) for row in rows],
                'total': total, 'offset': offset, 'limit': limit}

    def detail(self, knowledge_id):
        pair = self.session.execute(select(OrganizationItem, Knowledge).join(
            Knowledge, OrganizationItem.knowledge_id == Knowledge.id).where(Knowledge.id == knowledge_id)).first()
        if not pair or pair[1].deleted_at:
            return None, False
        eligible = self.session.scalar(text('SELECT k.id' + BASE + ' AND k.id=:id LIMIT 1'), {'id': knowledge_id})
        return pair, bool(eligible)
