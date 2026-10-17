"""Conflict, validation, read-only and teardown behavior without real credentials."""

from playwright.sync_api import expect
from settings_ui_checks import SECRET, profiles, open_profile, secret_not_exposed


def check_conflicts_and_errors(page, api, evidence):
    expect(profiles(page)).to_have_count(4)
    first = open_profile(page)
    first.get_by_test_id('profile-model').fill('local-unsubmitted-model')
    first.get_by_test_id('profile-key').fill(SECRET)
    get_count = len([call for call in api.calls if call['method'] == 'GET' and call['path'].endswith('/settings/ai')])
    api.next_error = (409, {'code': 'configuration_changed', 'unsafe': SECRET})
    page.get_by_test_id('ai-settings-save').click()
    expect(page.get_by_test_id('ai-settings-reload')).to_be_visible()
    expect(first.get_by_test_id('profile-model')).to_have_value('local-unsubmitted-model')
    expect(first.get_by_test_id('profile-key')).to_have_value(SECRET)
    assert len([call for call in api.calls if call['method'] == 'GET' and call['path'].endswith('/settings/ai')]) == get_count
    secret_not_exposed(page)
    page.get_by_test_id('ai-settings-reload').click()
    page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
    expect(first.get_by_test_id('profile-key')).to_have_value(SECRET)
    api.document['revision'] = 'external-revision'
    api.document['profiles'][0]['model'] = 'server-latest-model'
    page.get_by_test_id('ai-settings-reload').click()
    page.get_by_role('dialog').get_by_role('button', name='重新读取', exact=True).click()
    first = open_profile(page)
    expect(first.get_by_test_id('profile-model')).to_have_value('server-latest-model')
    first = open_profile(page)
    expect(first.get_by_test_id('profile-key')).to_have_value('')
    first.get_by_test_id('profile-key').fill(SECRET)
    first.locator('.settings-advanced > summary').click()
    first.get_by_test_id('profile-extra_body').fill('{ bad json')
    before = len(api.payloads)
    page.get_by_test_id('ai-settings-save').click()
    expect(page.get_by_text('扩展请求参数必须是有效的 JSON 对象。', exact=True)).to_be_visible()
    assert len(api.payloads) == before
    first.get_by_test_id('profile-extra_body').fill('{}')
    for status in [422, 503]:
        api.next_error = (status, {'code': 'synthetic_failure', 'input': SECRET})
        page.get_by_test_id('ai-settings-save').click()
        expect(page.get_by_test_id('ai-settings-save')).to_be_enabled()
        page.wait_for_timeout(250)
        assert len(api.payloads) == before + 1
        assert api.payloads[-1]['body']['expected_revision'] == 'external-revision'
        before += 1
        expect(first.get_by_test_id('profile-key')).to_have_value(SECRET)
        secret_not_exposed(page)
    return {'status': 'passed', 'conflict_does_not_reload_or_replace_revision': True, 'local_inputs_retained': True,
            'explicit_confirmed_reload': True, 'invalid_extra_zero_writes': True, 'validation_and_service_errors_no_retry': True,
            'unsafe_error_content_not_echoed': True}


def check_readonly_and_navigation(page, api, evidence):
    expect(profiles(page)).to_have_count(4)
    first = open_profile(page)
    first.get_by_test_id('profile-key').fill(SECRET)
    page.evaluate('window.__oldPassword = document.querySelector("[data-testid=profile-key]")')
    page.locator('#navigation a[href="#/knowledge"]').click()
    expect(page.get_by_role('dialog', name='离开编辑页面', exact=True)).to_be_visible()
    page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
    expect(first.get_by_test_id('profile-key')).to_have_value(SECRET)
    page.locator('#navigation a[href="#/knowledge"]').click()
    page.get_by_role('dialog').get_by_role('button', name='离开', exact=True).click()
    expect(page.get_by_role('heading', name='知识笔记', exact=True)).to_be_visible()
    assert page.evaluate('window.__oldPassword.value') == ''
    assert not api.payloads
    page.set_viewport_size({'width': 390, 'height': 1000})
    page.get_by_test_id('mobile-settings-link').click()
    expect(profiles(page)).to_have_count(4)
    expect(page.get_by_test_id('mobile-settings-link')).to_have_attribute('aria-current', 'page')
    expect(open_profile(page).get_by_test_id('profile-key')).to_have_value('')
    api.document.update(editable=False, read_only_reason='configuration_read_only', environment_overrides=['MEMORY_OS_AI_ENABLED'])
    page.reload(); expect(profiles(page)).to_have_count(4)
    expect(page.get_by_test_id('ai-settings-save')).to_be_disabled()
    expect(page.get_by_test_id('ai-add-profile')).to_be_disabled()
    expect(open_profile(page).get_by_test_id('profile-key')).to_be_disabled()
    expect(page.get_by_text('当前配置由启动环境或宿主机管理，请在本机配置文件中修改并重启。', exact=True)).to_be_visible()
    assert page.locator('#main script').count() == 0
    page.get_by_test_id('ai-settings-save').evaluate('node => node.click()')
    assert not api.payloads
    secret_not_exposed(page)
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(evidence / 'settings-readonly-390.png'), full_page=True, animations='disabled')
    return {'status': 'passed', 'dirty_cancel_preserves_input': True, 'confirmed_leave_clears_detached_password': True,
            'mobile_navigation_without_drawer': True, 'read_only_all_mutations_disabled': True}


def check_late_load(page, api, evidence):
    expect(profiles(page)).to_have_count(4)
    page.locator('#navigation a[href="#/knowledge"]').click()
    expect(page.get_by_role('heading', name='知识笔记', exact=True)).to_be_visible()
    api.hold_get = True
    page.get_by_test_id('desktop-settings-link').click()
    expect(page.get_by_text('正在读取本机设置…', exact=True)).to_be_visible()
    page.locator('#navigation a[href="#/knowledge"]').click()
    expect(page.get_by_role('heading', name='知识笔记', exact=True)).to_be_visible()
    while api.pending_gets:
        try: api.complete_get()
        except Exception: pass  # The departed page intentionally aborted its own GET.
    page.wait_for_timeout(100)
    expect(profiles(page)).to_have_count(0)
    expect(page.get_by_role('heading', name='知识笔记', exact=True)).to_be_visible()
    return {'status': 'passed', 'late_settings_response_ignored': True}


def check_save_during_navigation(page, api, evidence):
    expect(profiles(page)).to_have_count(4)
    first = open_profile(page)
    first.get_by_test_id('profile-model').fill('save-during-navigation')
    first.get_by_test_id('profile-key').fill(SECRET)
    api.hold_put = True
    page.get_by_test_id('ai-settings-save').click()
    expect(page.get_by_test_id('ai-settings-save')).to_be_disabled()
    page.locator('#navigation a[href="#/knowledge"]').click()
    expect(page.get_by_role('dialog', name='离开编辑页面', exact=True)).to_be_visible()
    api.complete_put()
    page.wait_for_timeout(80)
    page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
    expect(page.get_by_test_id('ai-settings-save')).to_be_enabled()
    expect(page.get_by_text('配置已保存 · 等待重启', exact=True)).to_be_visible()
    expect(open_profile(page).get_by_test_id('profile-key')).to_have_value('')
    assert not page.evaluate('window.memoryOsHasUnsavedChanges()')
    assert len(api.payloads) == 1
    secret_not_exposed(page)
    return {'status': 'passed', 'save_response_while_navigation_dialog': True,
            'cancel_navigation_restores_saved_form': True, 'single_request_without_retry': True}
