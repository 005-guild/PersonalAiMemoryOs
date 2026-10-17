"""File API and DOM checks for Markdown uploads and immutable preview bytes."""

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from playwright.sync_api import expect


def md(name='note.md', content=b'# Synthetic\nOriginal offline body.'):
    return {'name': name, 'mimeType': 'text/markdown', 'buffer': content}


def choose_mode(page):
    page.get_by_role('tab', name='知乎 Markdown 文件夹', exact=True).click()


def check_large_directory(page, api, evidence: Path):
    folder = evidence / '导出目录'
    (folder / 'nested').mkdir(parents=True)
    for index in range(571):
        path = (folder / 'nested' if index % 2 else folder) / f'{index:04d}.md'
        path.write_text('# 合成正文\n仅用于浏览器边界验收。', encoding='utf-8')
    (folder / 'README.md').write_text('ignored', encoding='utf-8')
    (folder / 'export-progress.json').write_text('{}', encoding='utf-8')
    (folder / 'image.png').write_bytes(b'ignored media')
    choose_mode(page)
    page.get_by_test_id('import-directory').set_input_files(folder)
    expect(page.get_by_test_id('import-preview')).to_be_enabled(timeout=30000)
    expect(page.get_by_text('可提交 571 个 MD', exact=False)).to_be_visible()
    page.get_by_test_id('import-preview').click()
    expect(page.get_by_test_id('import-report')).to_contain_text('预计创建 571')
    assert len(api.calls) == 1
    payload = json.loads(api.calls[0]['bytes'])
    assert set(payload) == {'files'} and len(payload['files']) == 571
    assert len(api.calls[0]['bytes']) <= 10 * 1024 * 1024
    assert not any(item['relative_path'].lower().endswith(('readme.md','.png','.json')) for item in payload['files'])
    expect(page.get_by_test_id('import-report').locator('tbody tr')).to_have_count(50)
    page.get_by_role('button', name='报告下一页', exact=True).click()
    expect(page.get_by_test_id('import-report')).to_contain_text('第 2 页')
    (folder / '0000.md').write_text('CHANGED ON DISK AFTER PREVIEW', encoding='utf-8')
    page.get_by_test_id('import-submit').click()
    expect(page.get_by_test_id('import-report')).to_contain_text('已创建 571')
    assert len(api.calls) == 2 and api.calls[0]['bytes'] == api.calls[1]['bytes']
    with page.expect_download() as download:
        page.get_by_role('button', name='下载报告', exact=True).click()
    saved = evidence / 'large-report.json'
    download.value.save_as(saved)
    text = saved.read_text(encoding='utf-8')
    assert 'RAW_BODY_NEVER_DOWNLOAD' not in text and len(json.loads(text)['items']) == 571
    page.set_viewport_size({'width': 390, 'height': 1000})
    page.screenshot(path=str(evidence / 'large-directory-390.png'), full_page=True, animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    return {'status': 'passed', 'files_uploaded': 571, 'readme_and_media_excluded': True,
            'same_bytes_after_disk_change': True, 'report_paginated': 50, 'download_has_no_source_body': True}


def check_read_errors_and_partial(page, api, evidence):
    choose_mode(page)
    page.get_by_test_id('import-markdown-files').set_input_files([
        md('bom.md', b'\xef\xbb\xbf' + '中文正文'.encode()), md('invalid-utf8.md', b'\xff\xfe\xff'), md('last.md')])
    expect(page.get_by_test_id('import-preview')).to_be_enabled()
    expect(page.get_by_test_id('import-local-errors')).to_contain_text('invalid-utf8.md')
    api.invalid_last = True
    api.malicious = True
    page.get_by_test_id('import-preview').click()
    expect(page.get_by_test_id('import-report')).to_contain_text('预计创建 1')
    expect(page.get_by_test_id('import-report')).to_contain_text('无效 1')
    payload = json.loads(api.calls[0]['bytes'])
    assert len(payload['files']) == 2 and payload['files'][0]['content'] == '中文正文'
    assert page.evaluate('window.__unsafeImport') is None
    assert page.get_by_test_id('import-report').locator('img,script,svg').count() == 0
    api.partial = True
    page.get_by_test_id('import-submit').click()
    expect(page.get_by_test_id('import-report')).to_contain_text('已处理 1/2 条')
    expect(page.get_by_test_id('import-report')).to_contain_text('1 个文件本地读取失败，未上传')
    expect(page.get_by_test_id('import-submit')).to_be_disabled()
    assert len(api.calls) == 2 and api.calls[0]['bytes'] == api.calls[1]['bytes']
    with page.expect_download() as download:
        page.get_by_role('button', name='下载报告', exact=True).click()
    saved = evidence / 'partial-report.json'
    download.value.save_as(saved)
    data = json.loads(saved.read_text(encoding='utf-8'))
    assert data['local_read_failed'] == 1 and data['local_read_errors'][0]['relative_path'] == 'invalid-utf8.md'
    assert 'RAW_BODY_NEVER_DOWNLOAD' not in saved.read_text(encoding='utf-8')
    page.set_viewport_size({'width': 390, 'height': 1000})
    page.screenshot(path=str(evidence / 'partial-report-390.png'), full_page=True, animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    return {'status': 'passed', 'utf8_bom': True, 'local_failure_not_uploaded': True, 'partial_503_visible': True,
            'automatic_retries': 0, 'xss_not_executed': True, 'report_has_local_failure_metadata': True}


def check_selection_races(page, api, evidence):
    page.evaluate('''() => {const original=File.prototype.arrayBuffer;File.prototype.arrayBuffer=function(){
        if(this.name==='slow.md')return new Promise(resolve=>{window.releaseSlow=()=>original.call(this).then(resolve);});
        return original.call(this);};}''')
    choose_mode(page)
    page.get_by_test_id('import-markdown-files').set_input_files(md('slow.md'))
    expect(page.get_by_test_id('import-preview')).to_be_disabled()
    page.get_by_role('tab', name='协议 JSON', exact=True).click()
    raw = b'{"schema_version":1,"items":[{"url":"https://www.zhihu.com/question/1/answer/2","title":"JSON","content":"original"}]}'
    page.get_by_test_id('import-file').set_input_files({'name':'valid.json','mimeType':'application/json','buffer':raw})
    expect(page.get_by_test_id('import-preview')).to_be_enabled()
    page.evaluate('window.releaseSlow()')
    page.get_by_test_id('import-preview').click()
    expect(page.get_by_test_id('import-submit')).to_be_enabled()
    assert api.calls[-1]['bytes'] == raw and '/zhihu?' in api.calls[-1]['url']
    choose_mode(page)
    expect(page.get_by_test_id('import-submit')).to_be_disabled()
    page.get_by_test_id('import-markdown-files').set_input_files(md('slow.md'))
    page.get_by_test_id('import-markdown-files').set_input_files(md('fast.md', b'fast content'))
    expect(page.get_by_test_id('import-preview')).to_be_enabled()
    page.evaluate('window.releaseSlow()')
    api.hold = True
    page.get_by_test_id('import-preview').click()
    expect(page.get_by_role('tab', name='协议 JSON', exact=True)).to_be_disabled()
    expect(page.get_by_test_id('import-markdown-files')).to_be_disabled()
    page.get_by_test_id('import-preview').dispatch_event('click')
    assert len(api.pending) == 1
    api.hold = False
    api.finish(api.pending.pop())
    expect(page.get_by_test_id('import-submit')).to_be_enabled()
    payload = json.loads(api.calls[-1]['bytes'])
    assert payload['files'] == [{'relative_path':'fast.md','content':'fast content'}]
    page.get_by_test_id('import-markdown-files').set_input_files(md('new.md'))
    expect(page.get_by_test_id('import-submit')).to_be_disabled()
    expect(page.get_by_test_id('import-preview')).to_be_enabled()
    directory = evidence/'again-A'
    directory.mkdir();(directory/'A.md').write_text('A original',encoding='utf-8')
    page.get_by_test_id('import-directory').set_input_files(directory)
    expect(page.get_by_test_id('import-preview')).to_be_enabled()
    assert page.get_by_test_id('import-markdown-files').input_value() == ''
    page.get_by_test_id('import-markdown-files').set_input_files(md('B.md',b'B original'))
    expect(page.get_by_test_id('import-preview')).to_be_enabled()
    assert page.get_by_test_id('import-directory').input_value() == ''
    page.get_by_test_id('import-directory').set_input_files(directory)
    expect(page.get_by_test_id('import-preview')).to_be_enabled()
    assert page.get_by_test_id('import-markdown-files').input_value() == ''
    page.get_by_test_id('import-preview').click()
    expect(page.get_by_test_id('import-submit')).to_be_enabled()
    assert json.loads(api.calls[-1]['bytes'])['files'][0]['content'] == 'A original'
    return {'status':'passed','old_mode_read_ignored':True,'old_selection_read_ignored':True,
            'new_selection_invalidates_preview':True,'busy_no_duplicate_request':True,'json_compatibility':True,
            'directory_A_multiselect_B_directory_A':True}


def check_request_limits(page, api, evidence):
    choose_mode(page)
    page.evaluate('''() => {window.reads=0;const original=File.prototype.arrayBuffer;File.prototype.arrayBuffer=function(){window.reads++;return original.call(this);};}''')
    page.get_by_test_id('import-markdown-files').set_input_files([md(f'{index}.md', b'x') for index in range(1001)])
    expect(page.get_by_text('Markdown 文件超过 1,000 个', exact=False)).to_be_visible()
    assert page.evaluate('window.reads') == 0
    page.get_by_test_id('import-markdown-files').set_input_files(md('oversize.md', b'x'*(10*1024*1024+1)))
    expect(page.get_by_text('Markdown 原始文件总大小超过 10 MiB', exact=False)).to_be_visible()
    assert page.evaluate('window.reads') == 0
    page.get_by_test_id('import-markdown-files').set_input_files(md('escaped.md', b'\x00'*(2*1024*1024)))
    expect(page.get_by_text('序列化后的请求超过 10 MiB', exact=False)).to_be_visible()
    expect(page.get_by_test_id('import-preview')).to_be_disabled()
    assert not api.calls
    return {'status':'passed','count_before_read':True,'raw_size_before_read':True,'serialized_size_bounded':True,'no_posts':True}


def check_legacy_json(page, api, evidence):
    from v06_browser_safeguards import check_partial_import
    path = evidence/'legacy.json'
    payload = {'schema_version':1,'items':[
        {'url':'https://www.zhihu.com/question/1/answer/2','title':'旧版JSON','content':'保留原始字节'},
        {'url':'https://invalid.example/','title':'无效条目','content':'脱敏样例'}]}
    path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    api.invalid_last = True
    origin = urlsplit(page.url)
    base = origin.scheme+'://'+origin.netloc

    class App:
        base_url = base
        def request(self, method, resource, body):
            return api.report(SimpleNamespace(url=base+resource,post_data_buffer=json.dumps(body).encode()))

    check_partial_import(page,App(),path)
    return {'status':'passed','existing_v06_partial_import_guard':True,'legacy_testids_retained':True}
