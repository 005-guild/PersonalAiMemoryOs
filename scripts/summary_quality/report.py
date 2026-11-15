"""Offline escaped comparison reports; model text is never executable HTML."""
from html import escape
from pathlib import Path
from scripts.summary_quality.generation import markdown
from scripts.summary_quality.storage import load,save

CRITERIA = ['忠实性','完整度','结构','可读性','原文依据']


def render(packet,results,review,budget,directory):
    directory = Path(directory)
    assessments = {row['identity']:row for row in review['articles']}
    accepted = sum(row.get('outcome')=='improved' for row in assessments.values())
    all_reviewed = len(assessments)==10 and all(row.get('outcome') in {'improved','same'} and
        set(row.get('scores',{}))==set(CRITERIA) and all(type(n) is int and 1<=n<=5 for n in row['scores'].values())
        and not row.get('fatal_findings') for row in assessments.values())
    gate = len(results)==10 and all(row['status']=='succeeded' for row in results.values()) and all_reviewed and accepted>=8
    spent = sum(row['accounted_micros'] for row in budget.get('calls',[]))/1e6
    header = f'10 篇摘要质量试点 · 已生成 {sum(x["status"]=="succeeded" for x in results.values())}/10 · 保守记账 ¥{spent:.6f} / ¥5'
    notice = '推广门槛已达到，仍需用户审核决定是否采纳。' if gate else '尚未达到推广门槛；现有收藏未被替换。'
    articles,md = [],['# '+header,'',notice,'','本报告为独立候选对照，图片识读不是逐字原文。','']
    for index,sample in enumerate(packet['samples'],1):
        identity=sample['identity'];result=results.get(identity,{'status':'not_run'});assessment=assessments[identity]
        current=sample['current'];candidate=result.get('candidate')
        enhanced=markdown(candidate) if candidate else '尚未生成：'+result.get('error',result['status'])
        quality='\n'.join([f"审核结论：{assessment.get('outcome','pending')}",
            *[f'{key}：{assessment.get("scores",{}).get(key,"待评")} / 5' for key in CRITERIA],
            '评价：'+assessment.get('notes','待审核'), '严重问题：'+('；'.join(assessment.get('fatal_findings',[])) or '尚未记录')])
        charge=result.get('accounted_micros',0)/1e6
        def panel(title,text):return f'<section><h3>{escape(title)}</h3><div class="panel-body"><pre>{escape(text)}</pre></div></section>'
        def paragraphs(text):return ''.join('<p>'+escape(part)+'</p>' for part in text.split('\n') if part.strip())
        if candidate:
            content='<h4>短提要</h4>'+paragraphs(candidate['summary'])+'<h4>文章概述</h4>'+paragraphs(candidate['overview'])
            for point in candidate['points']:
                content+='<h4>'+escape(point['heading'])+'</h4>'+paragraphs(point['detail'])+'<small>依据：'+escape('、'.join(point['evidence_ids']))+'</small>'
            content+='<h4>条件与局限</h4>'+paragraphs(candidate['conditions'])+'<h4>作者结论</h4>'+paragraphs(candidate['conclusion'])+'<h4>原文依据</h4>'
            content+=''.join('<blockquote>'+escape(q['id']+'：'+q['quote'])+'</blockquote>' for q in candidate['source_quotes'])
            if candidate['image_evidence_ids']:content+='<p>图片识读依据（非逐字原文）：'+escape('、'.join(candidate['image_evidence_ids']))+'</p>'
            candidate_panel='<section><h3>增强摘要候选</h3><div class="panel-body">'+content+'</div></section>'
        else:candidate_panel=panel('增强摘要候选',enhanced)
        images=[]
        for path in sample['files']:
            file=Path(path)
            if file.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif'}:
                images.append(f'<a href="{escape(file.as_uri(),quote=True)}"><img loading="lazy" src="{escape(file.as_uri(),quote=True)}" alt="本地原图"></a>')
        observations='\n'.join(row['id']+'（清晰识读，非逐字引文）：'+row['text'] for row in sample['observations'])
        articles.append(f'<article id="sample-{index}"><header><small>{escape(sample["kind"])} · {escape(identity)}</small>'
            f'<h2>{index}. {escape(current["title"])}</h2><p>{escape(current["category"])} · 单篇记账 ¥{charge:.6f}</p></header>'
            '<div class="comparison">'+panel('原文 · '+sample['original']['title'],sample['original']['content'])+
            panel('现有摘要与笔记',current['summary']+'\n\n'+current['body'])+candidate_panel+'</div>'+
            (f'<details><summary>本地原图与既有清晰识读</summary><div class="images">'+''.join(images)+'</div><pre>'+escape(observations)+'</pre></details>' if images else '')+
            panel('质量评价',quality)+f'<a href="#top">返回目录 ↑</a></article>')
        md += [f'## {index}. {current["title"]}',f'{sample["kind"]} · {identity} · 单篇 ¥{charge:.6f}','',
               '### 原文',sample['original']['content'],'','### 现有摘要与笔记',current['summary'],current['body'],'',
               '### 增强候选',enhanced,'','### 质量评价',quality,'']
    nav=''.join(f'<li><a href="#sample-{i}">{escape(s["current"]["title"])}</a></li>' for i,s in enumerate(packet['samples'],1))
    css='''body{margin:0;background:#f6f4ed;color:#263b31;font:16px/1.85 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1700px;margin:auto;padding:32px}h1{font-size:28px}h2{font-size:25px}h3{font-size:17px}h4{margin:20px 0 8px}p{white-space:pre-wrap}blockquote{margin:12px 0;padding:8px 14px;border-left:3px solid #a9b99a;background:#f0f3e9}a{color:#285542}article{border-top:2px solid #ced7c4;margin:40px 0;padding:24px 0}.comparison{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}section{min-width:0;background:#fffdf7;border:1px solid #dce1d2;padding:18px;border-radius:8px}.panel-body{max-height:78vh;overflow:auto;overflow-wrap:anywhere}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}small{color:#697564}details{margin:20px 0}.images{display:flex;flex-wrap:wrap;gap:12px}.images img{height:180px;max-width:240px;object-fit:contain}.notice{background:#e6ecdc;padding:18px}@media(max-width:1000px){.comparison{grid-template-columns:1fr}main{padding:20px}}'''
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+\
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src file: data:; style-src \'unsafe-inline\'; base-uri \'none\'">'+\
        '<title>摘要质量对照报告</title><style>'+css+'</style><main id="top"><h1>'+escape(header)+'</h1><p class="notice">'+escape(notice)+\
        '</p><p>保留现有标题、分类、标签与正式收藏。文字引文按 Q 编号核对，O 编号是既有图片识读。</p><ol>'+nav+'</ol>'+''.join(articles)+'</main></html>'
    (directory/'report.html').write_text(html,encoding='utf-8')
    (directory/'report.md').write_text('\n'.join(md),encoding='utf-8')
    status={'generated':sum(row['status']=='succeeded' for row in results.values()),'total':10,
        'accounted_yuan':spent,'budget_yuan':5,'improved':accepted,'promotion_gate':gate,
        'reviewed':sum(row.get('outcome')!='pending' for row in assessments.values())}
    save(directory/'report-status.json',status)
    return status


def report(directory,budget_root):
    directory=Path(directory);packet=load(directory/'samples.json')
    results=load(directory/'results.json') if (directory/'results.json').exists() else {}
    review_path=directory/'review.json'
    if not review_path.exists():
        save(review_path,{'articles':[{'identity':sample['identity'],'outcome':'pending','scores':{},'notes':'','fatal_findings':[]} for sample in packet['samples']]})
    budget=load(Path(budget_root)/'budget.json') if (Path(budget_root)/'budget.json').exists() else {'calls':[]}
    return render(packet,results,load(review_path),budget,directory)
