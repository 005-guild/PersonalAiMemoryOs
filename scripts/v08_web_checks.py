"""Repeatable browser checks, reusable with an isolated frozen EXE server."""
import json
import time
import re
import math
from urllib.parse import quote
from playwright.sync_api import expect


def seed(request):
    sources=[]
    for index in range(105):
        sources.append(request('POST','/api/v1/sources',{'title':f'v07 合成来源 {index:03d}','author':f'作者{index}','source_type':'manual','content':f'离线验收原文 {index}，用于精确引用，不含个人数据。'}))
    for index in range(25):
        request('POST','/api/v1/sources',{'title':'同标题惰性预览','author':f'回答作者{index}','source_type':'manual','content':f'只有点击展开才应读取的正文 {index}。'})
    for index in range(25):
        request('POST','/api/v1/knowledge',{'title':f'分页笔记 {index:03d}','body':'# 离线合成笔记\n\n数据库是索引依据。','source_ids':[]})
    last={}
    for purpose in ('knowledge','rag_qa'):
        for index in range(105):
            last[purpose]=request('POST','/api/v1/prompt-templates',{'purpose':purpose,'name':f'{purpose} 模板 {index:03d}','content':'忠实分析，明确事实与推论。' if purpose=='knowledge' else '以简洁中文回答，保留引用并指出依据不足。','output_schema_version':2 if purpose=='knowledge' else 1})
    return {'sources':sources,'last':last}


def choose_sizes(nav, expected=(10,20,50,100)):
    for size in expected:
        match=re.search(r'共\s*(\d+)\s*条',nav.inner_text());total=int(match.group(1))if match else 0
        nav.get_by_role('combobox').select_option(str(size))
        expect(nav.get_by_role('combobox')).to_have_value(str(size))
        expect(nav).to_contain_text(f'第 1 / {max(1,math.ceil(total/size))} 页')


def run_checks(page, url, request, evidence, seeded, *, read_only=False, desktop_root=None):
    calls=[]
    page.on('request',lambda item:calls.append((item.method,item.url)))
    checks=[]
    page.goto(url+'/#/sources')
    nav=page.get_by_role('navigation',name='资料标题分页')
    choose_sizes(nav);nav.get_by_role('combobox').select_option('10')
    nav.get_by_label('跳转页码').fill('3');nav.get_by_role('button',name='跳转',exact=True).click()
    expect(page.get_by_role('navigation',name='资料标题分页')).to_contain_text('第 3 /')
    checks.append('source groups all sizes and page jump')
    page.goto(url+'/#/sources/group?title='+quote('同标题惰性预览'))
    expect(page.get_by_test_id('source-group-summary')).to_have_count(20)
    before=len([item for item in calls if '/api/v1/sources/' in item[1]])
    page.wait_for_timeout(150)
    assert len([item for item in calls if '/api/v1/sources/' in item[1]])==before
    page.get_by_test_id('source-group-summary').first.locator('summary').first.click()
    expect(page.get_by_test_id('source-group-card')).to_have_count(1)
    assert len([item for item in calls if '/api/v1/sources/' in item[1]])==before+1
    choose_sizes(page.get_by_role('navigation',name='同标题资料分页'))
    checks.append('group summaries lazy full body and all sizes')
    page.goto(url+'/#/knowledge');choose_sizes(page.get_by_role('navigation',name='知识笔记分页'))
    page.get_by_role('navigation',name='知识笔记分页').get_by_role('combobox').select_option('10')
    page.get_by_role('navigation',name='知识笔记分页').get_by_role('button',name='下一页',exact=True).click()
    page.locator('.record-title').first.click();page.get_by_test_id('editor-back').click()
    expect(page.get_by_role('navigation',name='知识笔记分页')).to_contain_text('第 2 /')
    checks.append('knowledge pagination retained after editor')
    page.goto(url+'/#/prompts')
    choose_sizes(page.get_by_role('navigation',name='提示词模板分页'))
    page.get_by_label('模板用途',exact=True).select_option('rag_qa')
    page.get_by_label('搜索提示词模板',exact=True).fill('rag_qa 模板 104')
    expect(page.get_by_test_id('prompt-open')).to_have_count(1)
    page.get_by_test_id('prompt-open').click();expect(page.get_by_test_id('prompt-content')).to_have_value('以简洁中文回答，保留引用并指出依据不足。')
    page.get_by_test_id('prompt-content').fill('V08 浏览器自定义回答结构：结论、依据与待验证项。')
    page.get_by_test_id('prompt-save').click();expect(page.get_by_text('模板已保存，新请求立即可用；没有调用模型。',exact=True)).to_be_visible()
    page.get_by_role('button',name='查看修订历史',exact=True).click();choose_sizes(page.get_by_role('navigation',name='模板修订历史分页'))
    held_revisions=[];revision_path=f'**/api/v1/prompt-templates/{seeded["last"]["rag_qa"]["id"]}/revisions?*'
    def hold_revision(route):
        if 'limit=10' in route.request.url:held_revisions.append((route,route.fetch().json()))
        else:route.continue_()
    page.route(revision_path,hold_revision)
    revision_nav=page.get_by_role('navigation',name='模板修订历史分页');revision_nav.get_by_role('combobox').select_option('10')
    for _ in range(50):
        if held_revisions:break
        page.wait_for_timeout(100)
    assert held_revisions
    revision_nav.get_by_role('combobox').select_option('50');expect(revision_nav.get_by_role('combobox')).to_have_value('50')
    page.wait_for_timeout(100)
    for route,payload in held_revisions:route.fulfill(status=200,content_type='application/json',body=json.dumps(payload,ensure_ascii=False))
    page.wait_for_timeout(100);expect(revision_nav.get_by_role('combobox')).to_have_value('50');page.unroute(revision_path)
    page.get_by_role('button',name='预览内容',exact=True).click()
    page.get_by_test_id('prompt-copy').click();page.get_by_test_id('prompt-save').click()
    expect(page.get_by_test_id('prompt-name')).to_have_value('rag_qa 模板 104（副本）')
    page.get_by_test_id('prompt-default').click();page.get_by_role('dialog').get_by_role('button',name='设为默认',exact=True).click();expect(page.get_by_test_id('prompt-default')).to_be_disabled()
    checks.append('two prompt purposes >100 search, edit, preview, copy, independent default, revision pagination')
    page.goto(url+'/#/processing')
    expect(page.get_by_test_id('processing-source-all')).to_be_visible()
    choose_sizes(page.get_by_role('navigation',name='来源资料分页'))
    page.get_by_test_id('processing-source-all').click()
    expect(page.get_by_text('当前页全选将超过 20 篇，请先清空或逐项选择。',exact=True)).to_be_visible()
    expect(page.get_by_text('已选 0 / 20 篇',exact=True)).to_be_visible()
    page.get_by_role('navigation',name='来源资料分页').get_by_role('combobox').select_option('10')
    page.locator(f'input[data-source-id="{seeded["sources"][0]["id"]}"]').count()
    # Search preserves selection while template lookup can reach beyond the first 100.
    page.get_by_test_id('processing-source-search').fill('v07 合成来源 000')
    expect(page.locator(f'input[data-source-id="{seeded["sources"][0]["id"]}"]')).to_be_visible()
    page.locator(f'input[data-source-id="{seeded["sources"][0]["id"]}"]').check()
    page.get_by_test_id('processing-template').get_by_label('搜索解析模板',exact=True).fill('knowledge 模板 104')
    page.get_by_test_id('processing-template').get_by_role('button',name='knowledge 模板 104 · v1',exact=True).click()
    expect(page.get_by_test_id('processing-template')).to_contain_text('已选：knowledge 模板 104')
    picker_nav=page.get_by_role('navigation',name='解析模板选择分页')
    expect(picker_nav.get_by_role('button',name='上一页',exact=True)).to_be_disabled();expect(picker_nav.get_by_role('button',name='下一页',exact=True)).to_be_disabled()
    page.get_by_test_id('processing-generate').click();page.get_by_role('dialog').get_by_role('button',name='开始生成',exact=True).click()
    expect(page.get_by_test_id('processing-batch-detail')).to_be_visible()
    identifier=page.url.split('batch_id=')[1]
    for _ in range(150):
        batch=request('GET','/api/v1/processing/batches/'+identifier)
        if batch['status']=='completed':break
        if batch['status']=='paused':raise AssertionError(batch)
        time.sleep(.1)
    assert batch['counts']['ready']==1
    choose_sizes(page.get_by_role('navigation',name='批次任务分页'))
    old_table=page.get_by_test_id('processing-batch-detail').locator('table').first.element_handle()
    page.get_by_test_id('processing-batch-detail').get_by_role('button',name='刷新列表',exact=True).click()
    page.wait_for_function('(node)=>!node.isConnected',arg=old_table)
    page.get_by_test_id('processing-batch-detail').get_by_text('历次尝试',exact=True).click()
    choose_sizes(page.get_by_role('navigation',name='任务尝试分页'))
    page.goto(url+'/#/drafts');expect(page.get_by_role('heading',name='草稿箱',exact=True)).to_be_visible()
    assert page.get_by_test_id('processing-generate').count()==0
    choose_sizes(page.get_by_role('navigation',name='草稿箱分页'))
    page.locator('a.record-title').first.click();expect(page.get_by_test_id('processing-adopt')).to_be_enabled()
    assert page.get_by_test_id('processing-generate').count()==0
    page.get_by_test_id('processing-adopt').click();expect(page.get_by_test_id('knowledge-body')).to_be_visible()
    page.get_by_test_id('knowledge-save').click();page.wait_for_url('**/#/')
    checks.append('generation >100 template choice, 100-size select rejection, task pagination, standalone draft, adopt/save overview')
    page.goto(url+'/#/settings');expect(page.get_by_test_id('rag-settings-save')).to_be_visible()
    assert page.get_by_test_id('prompt-new').count()==0
    choose_sizes(page.get_by_role('navigation',name='生成模型配置分页'));choose_sizes(page.get_by_role('navigation',name='向量配置分页'))
    if read_only:
        expect(page.get_by_test_id('rag-settings-save')).to_be_disabled();expect(page.get_by_test_id('ai-settings-save')).to_be_disabled()
    else:
        rag_nav=page.get_by_role('navigation',name='向量配置分页');rag_nav.get_by_role('combobox').select_option('10')
        page.get_by_test_id('rag-profile').first.locator('summary').first.click()
        page.get_by_test_id('embedding-label').first.fill('浏览器配置保存（隔离）')
        rag_nav.get_by_role('button',name='下一页',exact=True).click()
        page.get_by_test_id('rag-profile').first.locator('summary').first.click()
        page.get_by_test_id('embedding-label').first.fill('第二页尚未保存的配置')
        rag_nav.get_by_role('button',name='首页',exact=True).click()
        expect(page.get_by_test_id('embedding-label').first).to_have_value('浏览器配置保存（隔离）')
        held_save=[]
        def hold_rag_save(route):
            if route.request.method=='PUT':held_save.append((route,route.fetch().json()))
            else:route.continue_()
        page.route('**/api/v1/settings/rag',hold_rag_save)
        page.get_by_test_id('rag-settings-save').click()
        for _ in range(50):
            if held_save:break
            page.wait_for_timeout(100)
        assert held_save
        page.evaluate("location.hash='#/sources'");expect(page.get_by_role('dialog')).to_contain_text('有未保存的修改')
        for route,payload in held_save:route.fulfill(status=200,content_type='application/json',body=json.dumps(payload,ensure_ascii=False))
        page.wait_for_timeout(100);page.get_by_role('dialog').get_by_role('button',name='取消',exact=True).click()
        expect(page.get_by_text('RAG 配置已保存，没有调用模型或启动索引。',exact=True)).to_be_visible()
        page.unroute('**/api/v1/settings/rag')
        if desktop_root:page.get_by_role('dialog').get_by_role('button',name='稍后',exact=True).click()
        expect(page.get_by_test_id('rag-enabled')).not_to_be_checked()
        saved_settings=request('GET','/api/v1/settings/rag')
        assert len(saved_settings['profiles'])==22
        assert saved_settings['profiles'][0]['label']=='浏览器配置保存（隔离）'and saved_settings['profiles'][10]['label']=='第二页尚未保存的配置'
    page.get_by_test_id('rag-test-embedding').click();expect(page.get_by_role('dialog')).to_contain_text('最多一次 Embedding 调用')
    page.get_by_role('dialog').get_by_role('button',name='取消',exact=True).click()
    page.get_by_test_id('rag-test-embedding').click();page.get_by_role('dialog').get_by_role('button',name='调用一次',exact=True).click()
    expect(page.get_by_text('Embedding 测试通过：4 维，调用 1 次。',exact=True)).to_be_visible()
    checks.append(('Docker configuration is read-only with usable pagination'if read_only else'RAG setup save remains disabled and keeps every profile across pages')+'; explicit one-call Embedding probe and cancelled zero call')
    import_file=evidence/'browser-import.json'
    import_file.write_text(json.dumps({'schema_version':1,'items':[{'url':f'https://www.zhihu.com/question/77000/answer/{88000+index}','title':f'导入分页资料 {index:03d}','content':'本地合成正文，无真实资料。'}for index in range(25)]},ensure_ascii=False),encoding='utf-8')
    page.goto(url+'/#/imports');page.get_by_test_id('import-file').set_input_files(import_file);page.get_by_test_id('import-preview').click()
    expect(page.get_by_role('navigation',name='导入报告分页')).to_be_visible()
    before_imports=len([item for item in calls if '/api/v1/imports/zhihu?'in item[1]])
    choose_sizes(page.get_by_role('navigation',name='导入报告分页'))
    assert len([item for item in calls if '/api/v1/imports/zhihu?'in item[1]])==before_imports
    page.get_by_test_id('import-submit').click();expect(page.get_by_role('heading',name='导入报告',exact=True)).to_be_visible()
    if desktop_root:
        page.get_by_role('button',name='下载报告',exact=True).click()
        from verification_support import eventually
        downloaded=eventually(lambda:next(iter((desktop_root/'exports').glob('*report*.json')),None),timeout=15)
        assert len(json.loads(downloaded.read_text(encoding='utf-8'))['items'])==25
    else:
        with page.expect_download()as download:page.get_by_role('button',name='下载报告',exact=True).click()
        downloaded=download.value;downloaded.save_as(evidence/'downloaded-import-report.json')
        assert len(json.loads((evidence/'downloaded-import-report.json').read_text(encoding='utf-8'))['items'])==25
    checks.append('import report all sizes without resubmit and full report download')
    qa_calls=[]
    note=request('GET','/api/v1/knowledge?limit=1')['items'][0]
    hit={'knowledge_id':note['id'],'version':note['version'],'title':'安全引用标题 <script>window.__unsafeV08=1</script>','chunk_id':'synthetic-chunk','text':'这是本次检索的逐字依据。','score':.8,'path':None,'sources':[]}
    def search_stub(route):
        qa_calls.append(('search',route.request.post_data_json));route.fulfill(status=200,content_type='application/json',body=json.dumps({'items':[hit]*10,'index_incomplete':True},ensure_ascii=False))
    def ask_stub(route):
        qa_calls.append(('ask',route.request.post_data_json));route.fulfill(status=200,content_type='application/json',body=json.dumps({'insufficient_evidence':False,'paragraphs':[{'text':'严格根据片段作答。','citation_ids':['1']}],'citations':[{'citation_id':'1',**hit,'quote':hit['text']}],'profile_id':'local','model':'fixture-v08','prompt_template':{'id':route.request.post_data_json['prompt_template_id']}},ensure_ascii=False))
    page.route('**/api/v1/rag/index/status*',lambda route:route.fulfill(status=200,content_type='application/json',body='{"enabled":true}'))
    page.route('**/api/v1/rag/search',search_stub);page.route('**/api/v1/rag/ask',ask_stub)
    page.goto(url+'/#/search');page.get_by_test_id('search-query').fill('数据库索引');page.get_by_test_id('search-submit').click()
    choose_sizes(page.get_by_role('navigation',name='本次检索片段分页'))
    assert len(qa_calls)==1
    page.get_by_role('tab',name='引用问答',exact=True).click();page.get_by_test_id('ask-question').fill('如何建立知识索引？')
    page.get_by_test_id('ask-template').get_by_label('搜索问答模板',exact=True).fill('rag_qa 模板 104')
    page.get_by_test_id('ask-template').get_by_role('button',name='rag_qa 模板 104 · v2',exact=True).click()
    page.get_by_test_id('ask-submit').click();expect(page.get_by_test_id('ask-answer')).to_be_visible()
    qa_picker=page.get_by_role('navigation',name='问答模板选择分页')
    expect(qa_picker.get_by_role('button',name='上一页',exact=True)).to_be_disabled();expect(qa_picker.get_by_role('button',name='下一页',exact=True)).to_be_disabled()
    assert qa_calls[-1][1]['prompt_template_id']==seeded['last']['rag_qa']['id'] and qa_calls[-1][1]['prompt_template_version']==2
    choose_sizes(page.get_by_role('navigation',name='本次回答引用分页'));assert len(qa_calls)==2
    assert page.evaluate('window.__unsafeV08')is None
    page.get_by_role('link',name='查看引用 1',exact=True).click()
    page.get_by_test_id('ask-answer').locator('a[href^="#/knowledge/"]').first.click();expect(page.get_by_test_id('knowledge-body')).to_be_visible()
    page.unroute('**/api/v1/rag/index/status*');page.unroute('**/api/v1/rag/search');page.unroute('**/api/v1/rag/ask')
    checks.append('synthetic retrieval/QA transport: purpose-specific prompt, safe citation, result pagination zero repeat calls, citation navigation')
    page.goto(url+'/#/system')
    for name in ['记录分页','文件问题分页','笔记同步明细分页','索引错误分页','索引排除分页','模型状态分页']:
        for nav in page.get_by_role('navigation',name=name,exact=True).all():choose_sizes(nav)
    page.screenshot(path=str(evidence/'system-1440.png'),full_page=True)
    for route in ['prompts','drafts','processing','settings','search']:
        page.goto(url+'/#/'+route)
        if route=='processing':expect(page.get_by_test_id('processing-source-all')).to_be_visible()
        if route=='settings':expect(page.get_by_test_id('rag-settings-save')).to_be_visible()
        if route=='search':page.get_by_role('tab',name='引用问答',exact=True).click();expect(page.get_by_test_id('ask-template')).to_be_visible()
        for width in [1440,1024,390]:
            page.set_viewport_size({'width':width,'height':1000 if width>390 else 844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(route,width)
            page.screenshot(path=str(evidence/f'{route}-{width}.png'),full_page=True)
    checks.append('system detail pagination and 1440/1024/390 layout')
    page.goto(url+'/#/')
    page.evaluate("""async()=>{const {promptPicker}=await import('/assets/js/pages/prompt-picker.js');const host=document.createElement('section');host.dataset.testid='picker-busy-regression';document.body.append(host);window.__v08Picker=promptPicker({purpose:'knowledge'});host.append(window.__v08Picker.element);await window.__v08Picker.ready;}""")
    held_picker=[]
    def hold_picker(route):
        from urllib.parse import urlsplit,parse_qs
        if parse_qs(urlsplit(route.request.url).query).get('offset')==['20']:held_picker.append((route,route.fetch().json()))
        else:route.continue_()
    page.route('**/api/v1/prompt-templates?*',hold_picker)
    host=page.get_by_test_id('picker-busy-regression');host.get_by_role('button',name='下一页',exact=True).click()
    for _ in range(50):
        if held_picker:break
        page.wait_for_timeout(100)
    assert held_picker;page.evaluate('window.__v08Picker.busy(true)')
    row_id=held_picker[0][1]['items'][0]['id']
    for route,payload in held_picker:route.fulfill(status=200,content_type='application/json',body=json.dumps(payload,ensure_ascii=False))
    new_button=host.locator(f'button[data-template-id="{row_id}"]');expect(new_button).to_be_disabled()
    page.evaluate('window.__v08Picker.busy(false)');expect(new_button).to_be_enabled()
    expect(host.get_by_role('button',name='上一页',exact=True)).to_be_enabled()
    host.get_by_role('button',name='末页',exact=True).click();expect(host.get_by_role('button',name='下一页',exact=True)).to_be_disabled()
    page.unroute('**/api/v1/prompt-templates?*');page.evaluate('window.__v08Picker.destroy();document.querySelector(\'[data-testid="picker-busy-regression"]\').remove()')
    checks.append('template page arriving while busy unlocks new choices and preserves first/last pager boundaries')
    return checks
