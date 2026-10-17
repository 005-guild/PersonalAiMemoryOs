"""Synthetic group API used only by browser UI checks, with controllable body waits."""

import json
from urllib.parse import parse_qs, urlsplit

STAMP = '2026-10-17T00:00:00+00:00'
SHARED = '共同问题：多个回答'


class GroupUIAPI:
    def __init__(self):
        self.records = {}
        self.calls, self.pending = [], []
        self.hold_bodies = False
        self.active_bodies = self.maximum_bodies = 0
        for index in range(52):
            shared = index < 7
            identifier = f'10000000-0000-4000-8000-{index+1:012d}'
            body = ('# 独立回答\n答案 '+str(index)+' 的完整尾标记。')
            if index == 0:
                body += '\n<script>window.__unsafeSource=1</script>\n![远端](https://external.invalid/image.png)\n[危险](javascript:alert(1))'
            if index == 1:
                body = '长'*100001+'末尾不截断'
            self.records[identifier] = {'id':identifier, 'title':SHARED if shared else f'标题 {index-6:02d}',
                'source_type':'zhihu', 'author':'作者 '+str(index+1), 'url':f'https://www.zhihu.com/question/9/answer/{index+1}',
                'content':body, 'version':1, 'created_at':STAMP, 'updated_at':STAMP,
                'deleted_at': STAMP if index == 6 else None}

    @staticmethod
    def reply(route, value, status=200):
        route.fulfill(status=status,content_type='application/json',body=json.dumps(value,ensure_ascii=False))

    def visible(self, query):
        state=query.get('state',['active'])[0]
        return [record for record in self.records.values() if state=='all' or bool(record['deleted_at'])==(state=='deleted')]

    def summary(self, record):
        return {key:value for key,value in record.items() if key!='content'} | {'excerpt':record['content'][:80]}

    def finish_body(self, index=0):
        route, record=self.pending.pop(index)
        self.active_bodies-=1
        try:self.reply(route,record)
        except Exception:pass  # An aborted, disposed page intentionally ignores its old response.

    def handle(self, route):
        request=route.request
        parsed=urlsplit(request.url);query=parse_qs(parsed.query)
        path=parsed.path
        self.calls.append({'method':request.method,'path':path,'query':parsed.query})
        if path=='/health':return self.reply(route,{'status':'ok','database':'ok'})
        if path=='/api/v1/ui/source-groups':
            visible=[record for record in self.visible(query) if query.get('q',[''])[0] in record['title']]
            grouped={}
            for record in visible:grouped.setdefault(record['title'],[]).append(record)
            items=[{'title':title,'source_count':len(records),'active_count':sum(not item['deleted_at'] for item in records),
                    'deleted_count':sum(bool(item['deleted_at']) for item in records),'latest_updated_at':max(item['updated_at'] for item in records),
                    'source_types':sorted(set(item['source_type'] for item in records))} for title,records in sorted(grouped.items())]
            sort_by=query.get('sort_by',['updated_at'])[0];reverse=query.get('order',['desc'])[0]=='desc'
            keys={'title':lambda item:item['title'],'source_count':lambda item:item['source_count'],
                  'source_type':lambda item:min(item['source_types']),'updated_at':lambda item:item['latest_updated_at']}
            items.sort(key=keys[sort_by],reverse=reverse)
            offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['20'])[0])
            return self.reply(route,{'items':items[offset:offset+limit],'total':len(items),'total_sources':len(visible),'offset':offset,'limit':limit})
        if path=='/api/v1/ui/source-groups/items':
            records=[record for record in self.visible(query) if record['title']==query.get('title',[''])[0]]
            offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['5'])[0])
            return self.reply(route,{'items':[self.summary(record) for record in records[offset:offset+limit]],'total':len(records),'offset':offset,'limit':limit})
        if path.startswith('/api/v1/sources/'):
            key=path.split('/')[4];record=self.records[key]
            if request.method=='PATCH':
                changes=request.post_data_json
                if changes['expected_version']!=record['version']:return self.reply(route,{'detail':'stale_version'},409)
                record.update({key:value for key,value in changes.items() if key!='expected_version'});record['version']+=1
                return self.reply(route,record)
            if request.method=='POST' and path.endswith('/restore'):
                record['deleted_at']=None;record['version']+=1
                return self.reply(route,record)
            if self.hold_bodies:
                self.active_bodies+=1;self.maximum_bodies=max(self.maximum_bodies,self.active_bodies)
                self.pending.append((route,dict(record)));return
            return self.reply(route,record)
        if path=='/api/v1/ui/knowledge':return self.reply(route,{'items':[],'total':0,'offset':0,'limit':20})
        return self.reply(route,{'detail':'Unexpected group UI fixture '+path},404)
