"""Standalone deterministic Chat/Embedding fixture for browser deployment checks."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from threading import Lock

class Handler(BaseHTTPRequestHandler):
    calls=[]
    embedding_calls=0
    lock=Lock()
    def log_message(self,*args):pass
    def respond(self,status,value):
        raw=json.dumps(value,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.respond(200,{'status':'ok','version':'1.19.2'})
    def do_POST(self):
        try:
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/embeddings':
                result={'data':[{'index':index,'embedding':[1.,2.,3.,4.]}for index,_ in enumerate(payload['input'])],'usage':{'total_tokens':4}}
                with self.lock:type(self).embedding_calls+=1
                record={'endpoint':'embeddings','inputs':len(payload['input'])}
            elif self.path=='/chat/completions':
                sources=json.loads(payload['messages'][-1]['content'])['sources'];assert sources and all(item['title'].startswith('v07 合成来源')for item in sources)
                content={'title':'浏览器验收知识草稿','summary':'离线合成资料的完整知识分析。','category':'工程验收','tags':['隔离测试'],'concepts':['分页'],
                    'body':'# 完整分析\n\n资料来源与引用可追溯，人工采纳后才创建笔记。','source_quotes':[{'source_id':source['id'],'quote':source['content'][:30]}for source in sources]}
                result={'choices':[{'message':{'content':json.dumps(content,ensure_ascii=False)},'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':100,'total_tokens':200}}
                record={'endpoint':'chat','source_count':len(sources)}
                with self.lock:self.calls.append(record)
            else:self.respond(404,{'error':'unknown_fixture_endpoint'});return
            if getattr(self.server,'records',None):
                with self.lock:
                    with self.server.records.open('a',encoding='utf-8')as output:output.write(json.dumps(record)+'\n')
            self.respond(200,result)
        except (KeyError,ValueError,AssertionError,TypeError):self.respond(400,{'error':'synthetic_input_required'})

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,required=True);parser.add_argument('--records',type=Path,required=True);args=parser.parse_args()
    server=ThreadingHTTPServer((args.host,args.port),Handler);server.records=args.records
    try:server.serve_forever()
    finally:server.server_close()
if __name__=='__main__':main()
