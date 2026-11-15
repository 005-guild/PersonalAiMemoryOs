"""Read-only union of published collection notes and ordinary knowledge notes."""

import json
from sqlalchemy import text
from app.repositories.collection_views import ELIGIBLE, INDEXED_FROM, keyword_condition
from app.repositories.reading import CATEGORY, TOPIC, MONTH

ORDINARY = (" FROM knowledge k LEFT JOIN sync_states s ON s.knowledge_id=k.id WHERE k.deleted_at IS NULL "
            "AND (s.status IS NULL OR s.status NOT IN ('conflict','error')) "
            "AND NOT EXISTS(SELECT 1 FROM organization_items oi WHERE oi.knowledge_id=k.id)")
SOURCES = (" FROM sources src WHERE src.deleted_at IS NULL AND (src.id=k.source_id OR EXISTS("
           "SELECT 1 FROM knowledge_sources ks WHERE ks.knowledge_id=k.id AND ks.source_id=src.id))")


class AllReadingRepository:
    def __init__(self, session):
        self.session = session

    def query(self, *, scope='all', q='', topic='', category='', tag='', updated_month='', **ignored):
        params = {'needle': q.strip(), 'topic': topic, 'category': category, 'tag': tag, 'month': updated_month}
        branches = []
        for collection in ([True, False] if scope == 'all' else [scope == 'collection']):
            title = "coalesce(json_extract(o.snapshot,'$.values.title'),'')" if collection else "coalesce((SELECT src.title" + SOURCES + ' ORDER BY src.id LIMIT 1),\'\')'
            author = "json_extract(o.snapshot,'$.values.author')" if collection else '(SELECT src.author' + SOURCES + ' ORDER BY src.id LIMIT 1)'
            url = "json_extract(o.snapshot,'$.values.url')" if collection else '(SELECT src.url' + SOURCES + ' ORDER BY src.id LIMIT 1)'
            condition = keyword_condition(params['needle'], params) if collection else (
                " AND (:needle='' OR instr(lower(k.title||' '||k.summary||' '||k.body||' '||k.tags),lower(:needle))>0 "
                "OR EXISTS(SELECT 1" + SOURCES + " AND instr(lower(src.title||' '||src.content),lower(:needle))>0))")
            base = INDEXED_FROM + ' WHERE ' + ELIGIBLE if collection else ORDINARY
            filters = (f" AND (:topic='' OR {TOPIC}=:topic) AND (:category='' OR {CATEGORY}=:category)"
                       " AND (:tag='' OR EXISTS(SELECT 1 FROM json_each(k.tags) WHERE value=:tag))"
                       f" AND (:month='' OR {MONTH}=:month)")
            hit = (f"CASE WHEN :needle='' OR instr(lower(k.title||' '||{title}),lower(:needle))>0 THEN 'title' "
                   "WHEN instr(lower(k.summary),lower(:needle))>0 THEN 'summary' "
                   "WHEN instr(lower(k.tags),lower(:needle))>0 THEN 'tag' ELSE 'original' END")
            source_text = "coalesce(json_extract(o.snapshot,'$.values.content'),'')" if collection else "coalesce((SELECT group_concat(src.content,char(10))" + SOURCES + "),'')"
            excerpt = ("CASE WHEN :needle='' OR instr(lower(k.summary),lower(:needle))>0 THEN k.summary "
                       f"WHEN instr(lower(k.body),lower(:needle))>0 THEN k.body ELSE {source_text} END")
            columns = (f"SELECT k.id knowledge_id,k.title,substr(k.summary,1,600) summary,{CATEGORY} category,k.tags,"
                       f"k.updated_at,k.version,{title} source_title,{author} author,{url} source_url,"
                       f"'{('collection' if collection else 'other')}' source_kind,coalesce(s.status,'pending') sync_status,"
                       f"{hit} match_section,substr({excerpt},max(1,instr(lower({excerpt}),lower(:needle))-60),260) excerpt")
            branches.append(columns + base + filters + condition)
        return 'WITH candidates AS (' + ' UNION ALL '.join(branches) + ') ', params

    def notes(self, *, offset=0, limit=20, sort='updated_desc', **filters):
        cte, params = self.query(**filters)
        total = self.session.scalar(text(cte + 'SELECT count(*) FROM candidates'), params)
        order = 'title COLLATE NOCASE,knowledge_id' if sort == 'title_asc' else 'updated_at DESC,knowledge_id DESC'
        rows = self.session.execute(text(cte + 'SELECT * FROM candidates ORDER BY ' + order +
                                         ' LIMIT :limit OFFSET :offset'), {**params, 'limit': limit, 'offset': offset}).mappings()
        return {'items': [dict(r, tags=json.loads(r['tags'])) for r in rows], 'total': total, 'offset': offset, 'limit': limit}

    def overview(self, scope='all'):
        from collections import Counter
        cte, params = self.query(scope=scope)
        rows = self.session.execute(text(cte + "SELECT category,tags,strftime('%Y-%m',updated_at,'+8 hours') month FROM candidates"), params)
        categories, topics, tags, months = Counter(), Counter(), Counter(), set()
        for category, tag_json, month in rows:
            categories[category] += 1; topics[category.split('/', 1)[0]] += 1
            tags.update(set(json.loads(tag_json)))
            if month: months.add(month)
        counts = lambda values: [{'name': n, 'count': c} for n, c in sorted(values.items(), key=lambda x: (-x[1], x[0]))]
        total = sum(categories.values())
        where = '' if scope == 'all' else ('EXISTS' if scope == 'collection' else 'NOT EXISTS') + '(SELECT 1 FROM organization_items o WHERE o.knowledge_id=k.id) AND '
        active = self.session.scalar(text('SELECT count(*) FROM knowledge k WHERE ' + where + 'k.deleted_at IS NULL'))
        return {'total': total, 'unavailable_count': active-total, 'topics': counts(topics),
                'categories': [dict(x, topic=x['name'].split('/', 1)[0]) for x in counts(categories)],
                'tags': counts(tags), 'months': sorted(months, reverse=True), 'recent': self.notes(scope=scope, limit=6)['items']}

    def identities(self, **filters):
        cte, params = self.query(**filters)
        return set(self.session.scalars(text(cte + 'SELECT knowledge_id FROM candidates'), params))
