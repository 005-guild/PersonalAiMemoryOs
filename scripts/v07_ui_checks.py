"""Checks run in real Chromium with synthetic API transport."""
from playwright.sync_api import expect
from v07_ui_fixtures import uid


def checkbox(page, number):
    return page.locator(f'input[data-source-id="{uid(number)}"]')


def check_selection_and_batch(page, fixture, folder):
    expect(page.get_by_test_id('processing-generate')).to_be_disabled()
    expect(checkbox(page, 1)).to_be_visible()
    assert fixture.body_gets == [], 'selectors must not eagerly fetch full bodies'
    checkbox(page, 1).check(); checkbox(page, 2).check()
    page.get_by_role('button', name='预览正文', exact=True).first.click()
    expect(page.get_by_role('heading', name='资料 01', exact=True)).to_be_visible()
    assert fixture.body_gets == [uid(1)]
    assert page.locator('.source-selection-preview script,.source-selection-preview img').count() == 0
    page.get_by_role('button', name='下一页', exact=True).first.click()
    expect(checkbox(page, 21)).to_be_visible(); checkbox(page, 21).check()
    expect(page.get_by_text('已选 3 / 20 篇', exact=True)).to_be_visible()
    page.get_by_test_id('processing-source-all').click()
    expect(page.get_by_text('当前页全选将超过 20 篇，请先清空或逐项选择。')).to_be_visible()
    expect(page.get_by_text('已选 3 / 20 篇', exact=True)).to_be_visible()
    page.get_by_label('处理记录状态', exact=True).select_option('failed')
    expect(page.get_by_text('已选 3 / 20 篇', exact=True)).to_be_visible()
    page.get_by_test_id('processing-mode').select_option('merged')
    page.get_by_test_id('processing-max-tokens').fill('20000'); page.get_by_test_id('processing-timeout').fill('220')
    page.get_by_test_id('processing-generate').click()
    expect(page.get_by_role('dialog')).to_contain_text('预计最多 1 次模型调用')
    page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
    assert not fixture.batches
    page.get_by_test_id('processing-generate').click()
    page.get_by_role('dialog').get_by_role('button', name='开始生成', exact=True).click()
    expect(page.get_by_test_id('processing-batch-detail')).to_be_visible()
    payload = next(item['body'] for item in fixture.mutations if item['path'] == '/api/v1/processing/batches')
    assert payload['mode'] == 'merged' and [source['source_id'] for source in payload['sources']] == [uid(1),uid(2),uid(21)]
    assert payload['generation_settings'] == {'max_output_tokens': 20000, 'timeout_seconds': 220}
    assert payload['prompt_template_version'] == 1
    assert len(fixture.batches) == 1
    page.get_by_test_id('batch-continue').click(); page.get_by_role('dialog').get_by_role('button', name='确认调用', exact=True).click()
    expect(page.get_by_test_id('batch-continue')).to_be_enabled()
    call = next(item for item in fixture.mutations if item['path'].endswith('/continue'))
    assert call['body'] == {'expected_version': 1}
    page.get_by_test_id('batch-cancel').click(); page.get_by_role('dialog').get_by_role('button', name='取消后续', exact=True).click()
    expect(page.get_by_test_id('batch-detail-status') if page.get_by_test_id('batch-detail-status').count() else page.get_by_test_id('batch-cancel')).to_be_disabled()
    fixture.batches[0]['status']='paused';fixture.batches[0]['counts'].update(pending=0,failed=1)
    page.get_by_role('button',name='刷新进度',exact=True).click();expect(page.get_by_test_id('batch-retry')).to_be_enabled()
    page.get_by_test_id('batch-retry').click();expect(page.get_by_role('dialog')).to_contain_text('预计最多发起 1 次模型调用')
    page.get_by_role('dialog').get_by_role('button',name='取消',exact=True).click()
    assert not any(item['path'].endswith('/retry-failed') for item in fixture.mutations)
    version=fixture.batches[0]['version'];page.get_by_test_id('batch-retry').click();page.get_by_role('dialog').get_by_role('button',name='确认调用',exact=True).click()
    expect(page.get_by_test_id('batch-retry')).to_be_enabled()
    retries=[item for item in fixture.mutations if item['path'].endswith('/retry-failed')]
    assert len(retries)==1 and retries[0]['body']=={'expected_version':version}
    page.screenshot(path=str(folder/'processing-1440.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(folder/'processing-390.png'), full_page=True)
    return {'selection_cross_page': True, 'global_limit_20': True, 'lazy_safe_preview': True, 'separate_history_filter': True, 'cancelled_confirmation_zero_calls': True, 'merged_single_call_confirmation': True, 'overrides_above_defaults': True, 'continue_cancel_expected_version': True, 'explicit_retry_confirmation_and_version':True,'mobile_no_overflow': True}


def check_prompt_management(page, fixture, folder):
    expect(page.get_by_test_id('ai-settings-save')).to_be_visible()
    first = page.get_by_test_id('ai-profile').first
    first.locator('summary').first.click(); first.get_by_test_id('profile-label').fill('未保存的模型名称')
    page.get_by_test_id('prompt-new').click()
    page.get_by_test_id('prompt-name').fill('中文模板 <img onerror=window.__unsafeV07=1>')
    page.get_by_test_id('prompt-content').fill('忠实整理\n\n<script>window.__unsafeV07=1</script>')
    page.get_by_test_id('prompt-save').click()
    expect(page.get_by_text('模板已保存，新生成任务立即可用；没有调用模型。')).to_be_visible()
    assert page.evaluate('window.memoryOsHasUnsavedChanges()'), 'saving template must not clear dirty AI configuration'
    assert len(fixture.templates) == 2 and fixture.templates[-1]['output_schema_version'] == 2
    page.get_by_test_id('prompt-copy').click(); page.get_by_test_id('prompt-save').click()
    expect(page.get_by_test_id('prompt-name')).to_have_value('中文模板 <img onerror=window.__unsafeV07=1>（副本）')
    assert len(fixture.templates) == 3
    page.get_by_test_id('prompt-default').click(); page.get_by_role('dialog').get_by_role('button', name='设为默认', exact=True).click()
    expect(page.get_by_test_id('prompt-default')).to_be_disabled()
    assert fixture.templates[-1]['is_default']
    fixture.fail_next = 409
    page.get_by_test_id('prompt-content').fill('本地修改保留')
    page.get_by_test_id('prompt-save').click()
    expect(page.get_by_role('button', name='重新读取该模板')).to_be_visible()
    expect(page.get_by_test_id('prompt-content')).to_have_value('本地修改保留')
    assert page.evaluate('window.__unsafeV07') is None
    page.screenshot(path=str(folder/'prompts-1440.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844}); assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(folder/'prompts-390.png'), full_page=True)
    return {'template_create_copy_default': True, 'template_revision_conflict_keeps_input': True, 'independent_dirty_sections': True, 'xss_safe': True, 'mobile_no_overflow': True}


def check_note_sources(page, fixture, folder):
    expect(page.get_by_test_id('knowledge-title')).to_have_value('多来源笔记')
    expect(page.get_by_text('已选 2 / 20 篇', exact=True)).to_be_visible()
    checkbox(page, 3).check()
    page.get_by_test_id('knowledge-save').click()
    page.wait_for_url('**/#/')
    payload = next(item['body'] for item in fixture.mutations if item['method'] == 'PATCH')
    assert payload == {'source_ids': [uid(1),uid(2),uid(3)], 'expected_version': 3}
    page.goto(page.url.split('#')[0]+f'#/knowledge/{uid(200)}')
    expect(page.get_by_test_id('knowledge-save')).to_be_visible()
    page.get_by_test_id('knowledge-save').click(); page.wait_for_url('**/#/')
    assert sum(item['method']=='PATCH' for item in fixture.mutations) == 1
    return {'multiple_sources_saved': True, 'note_saved_returns_overview': True, 'no_change_save_returns_overview_without_write': True}


def check_restore_sources(page, fixture, folder):
    expect(page.get_by_test_id('entity-restore')).to_be_visible()
    expect(page.get_by_test_id('knowledge-source-all')).to_be_disabled()
    expect(page.get_by_test_id('knowledge-source-clear')).to_be_disabled()
    for box in page.locator('input[data-source-id]').all():expect(box).to_be_disabled()
    page.get_by_test_id('entity-restore').click()
    expect(page.get_by_role('button', name='解除已删除来源并恢复')).to_be_visible()
    page.get_by_role('button', name='解除已删除来源并恢复').click()
    page.get_by_role('dialog').get_by_role('button', name='确认', exact=True).click()
    expect(page.get_by_test_id('knowledge-save')).to_be_enabled()
    payload = next(item['body'] for item in fixture.mutations if item['path'].endswith('/restore'))
    assert payload == {'expected_version': 3, 'source_ids': [uid(1)]}
    return {'deleted_source_requires_explicit_unlink': True, 'remaining_source_preserved': True}


def check_restart_choice(page, fixture, folder):
    expect(page.get_by_test_id('ai-settings-save')).to_be_visible()
    page.get_by_test_id('ai-enabled').check(); page.get_by_test_id('ai-settings-save').click()
    expect(page.get_by_role('dialog')).to_contain_text('新的 AI 配置需要重启应用')
    page.get_by_role('dialog').get_by_role('button', name='稍后', exact=True).click()
    assert fixture.restart_requests == 0
    expect(page.get_by_text('当前 AI 已关闭',exact=True)).to_be_visible()
    page.get_by_test_id('ai-settings-save').click()
    page.get_by_role('dialog').get_by_role('button', name='现在重启', exact=True).click()
    expect(page.get_by_text('正在等待任务结束并重启应用…')).to_be_visible()
    assert fixture.restart_requests == 1
    call = next(item for item in fixture.mutations if item['path'].endswith('/desktop/restart'))
    assert call['body']['expected_revision'] == fixture.document['revision']
    assert all(not control.input_value() for control in page.get_by_test_id('profile-key').all())
    return {'later_no_restart_no_hot_apply': True, 'explicit_desktop_restart_once': True, 'saved_revision_used': True}


def check_selection_limit_and_failure(page, fixture, folder):
    expect(checkbox(page, 1)).to_be_visible()
    page.get_by_test_id('processing-source-all').check()
    expect(page.get_by_text('已选 20 / 20 篇',exact=True)).to_be_visible()
    page.get_by_role('button',name='下一页',exact=True).first.click();expect(checkbox(page,21)).to_be_visible()
    checkbox(page,21).click();expect(checkbox(page,21)).not_to_be_checked()
    expect(page.get_by_text('已选 20 / 20 篇',exact=True)).to_be_visible()
    search=page.get_by_test_id('processing-source-search');search.fill('资料 45')
    expect(checkbox(page,45)).to_be_visible();expect(page.get_by_text('已选 20 / 20 篇',exact=True)).to_be_visible()
    page.get_by_test_id('processing-source-clear').click();expect(page.get_by_text('已选 0 / 20 篇',exact=True)).to_be_visible()
    checkbox(page,45).focus();checkbox(page,45).press('Space');expect(checkbox(page,45)).to_be_checked()
    fixture.abort_batch=True
    page.get_by_test_id('processing-generate').evaluate('node=>{node.click();node.click();}')
    expect(page.get_by_role('dialog')).to_have_count(1)
    page.get_by_role('dialog').get_by_role('button',name='开始生成',exact=True).click()
    expect(page.get_by_text('未自动重试。若请求断连，请先查看持久批次和处理记录，确认是否已创建后再操作。')).to_be_visible()
    expect(page.get_by_test_id('processing-generate')).to_be_enabled()
    assert sum(item['path']=='/api/v1/processing/batches' for item in fixture.mutations)==1
    expect(page.get_by_text('已选 1 / 20 篇',exact=True)).to_be_visible()
    return {'current_page_all_20':True,'cross_page_limit':True,'search_retains_selection':True,'clear_all':True,'keyboard_checkbox':True,'one_confirmation':True,'network_failure_no_retry_preserves_selection':True}


def check_preview_race(page,fixture,folder):
    expect(checkbox(page,1)).to_be_visible();fixture.hold_preview=True
    buttons=page.get_by_role('button',name='预览正文',exact=True)
    buttons.nth(0).click();page.wait_for_timeout(30);buttons.nth(1).click();page.wait_for_timeout(30)
    assert len(fixture.pending_previews)==2
    route,value=fixture.pending_previews[1];fixture.reply(route,value)
    expect(page.get_by_role('heading',name='资料 02',exact=True)).to_be_visible()
    route,value=fixture.pending_previews[0]
    try:fixture.reply(route,value)
    except Exception:pass  # the previous fetch has already been explicitly aborted
    expect(page.get_by_role('heading',name='资料 02',exact=True)).to_be_visible()
    assert not page.get_by_role('heading',name='资料 01',exact=True).count()
    fixture.hold_sources=True;page.get_by_test_id('processing-source-search').fill('资料 4');page.wait_for_timeout(350)
    assert fixture.pending_sources
    page.evaluate("location.hash='#/knowledge'");expect(page.get_by_role('heading',name='知识笔记',exact=True)).to_be_visible()
    for route,value in fixture.pending_sources:
        try:fixture.reply(route,value)
        except Exception:pass
    assert page.url.endswith('#/knowledge')
    assert not page.get_by_test_id('processing-sources').count()
    return {'out_of_order_preview_ignored':True,'late_source_page_cannot_replace_new_route':True}


def check_initial_source_dirty(page,fixture,folder):
    expect(checkbox(page,1)).to_be_visible()
    page.get_by_test_id('processing-mode').select_option('merged')
    assert page.evaluate('window.memoryOsHasUnsavedChanges()')
    assert fixture.pending_previews
    for route,value in fixture.pending_previews:fixture.reply(route,value)
    expect(page.get_by_text('已选 1 / 20 篇',exact=True)).to_be_visible()
    assert page.evaluate('window.memoryOsHasUnsavedChanges()'), 'late initial source must not clear later edits'
    return {'late_initial_source_preserves_dirty':True}
