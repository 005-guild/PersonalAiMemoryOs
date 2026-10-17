"""Configuration editing checks using synthetic, explicitly intercepted APIs."""

import json
from playwright.sync_api import expect

SECRET = 'synthetic-ui-secret-not-a-real-credential'


def profiles(page): return page.get_by_test_id('ai-profile')


def open_profile(page, index=0):
    card = profiles(page).nth(index)
    if not card.evaluate('node => node.open'): card.locator('summary').first.click()
    return card


def secret_not_exposed(page):
    assert SECRET not in page.locator('body').inner_text()
    assert SECRET not in page.content()
    assert SECRET not in page.url
    assert page.evaluate('Object.keys(localStorage).length + Object.keys(sessionStorage).length') == 0
    for control in page.get_by_test_id('profile-key').all():
        expect(control).to_have_attribute('type', 'password')
        expect(control).to_have_attribute('autocomplete', 'new-password')
        assert control.get_attribute('value') is None


def check_roundtrip_and_busy(page, api, evidence):
    expect(profiles(page)).to_have_count(4)
    first = open_profile(page)
    expect(first.get_by_test_id('profile-key')).to_have_value('')
    expect(first.get_by_test_id('profile-key-state')).to_have_text('已配置（不会显示原值）')
    expect(page.get_by_test_id('ai-default-profile')).to_have_value('deepseek')
    expect(page.get_by_text('D:\\合成便携目录\\data\\memory.db', exact=True)).to_be_visible()
    expect(page.get_by_text('D:\\合成便携目录\\knowledge', exact=True)).to_be_visible()
    expect(open_profile(page, 3).get_by_test_id('profile-key')).to_be_disabled()
    assert page.evaluate('window.__unsafeSettings') is None
    assert page.locator('.settings-profile img,.settings-profile script').count() == 0
    original = {profile['id']: profile for profile in api.document['profiles']}
    api.hold_put = True
    first.get_by_test_id('profile-label').fill('编辑后的中文名称')
    page.get_by_test_id('ai-enabled').check()
    page.get_by_test_id('ai-settings-save').click()
    expect(page.get_by_test_id('ai-settings-save')).to_be_disabled()
    expect(first.get_by_test_id('profile-model')).to_be_disabled()
    page.get_by_test_id('ai-settings-save').evaluate('node => {node.click(); node.click();}')
    assert len(api.payloads) == 1 and len(api.pending_puts) == 1
    payload = api.payloads[0]
    assert payload['token'] == 'synthetic-csrf-token'
    assert payload['body']['expected_revision'] == 'revision-1'
    assert payload['body']['key_updates'] == []
    for profile in payload['body']['profiles']:
        expected = {**original[profile['id']], **({'label': '编辑后的中文名称'} if profile['id'] == 'deepseek' else {})}
        assert profile == expected, profile
    api.complete_put()
    expect(page.get_by_test_id('ai-settings-save')).to_be_enabled()
    expect(page.get_by_text('配置已保存 · 等待重启', exact=True)).to_be_visible()
    expect(page.get_by_text('当前 AI 已关闭', exact=True)).to_be_visible()
    expect(page.get_by_test_id('ai-enabled')).to_be_checked()
    assert all(control.input_value() == '' for control in page.get_by_test_id('profile-key').all())
    assert not page.evaluate('window.memoryOsHasUnsavedChanges()')
    assert 'synthetic-csrf-token' not in page.content()
    secret_not_exposed(page)
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(evidence / 'settings-1440.png'), full_page=True, animations='disabled')
    return {'status': 'passed', 'complete_four_protocol_roundtrip': True, 'advanced_parameters_preserved': True,
            'single_submit_while_busy': True, 'active_not_hot_applied': True, 'keys_retained_without_echo': True, 'xss_as_text': True}


def check_presets_keys_and_mobile(page, api, evidence):
    expect(profiles(page)).to_have_count(4)
    page.get_by_label('新配置模板', exact=True).select_option('deepseek')
    page.get_by_test_id('ai-add-profile').click()
    expect(profiles(page)).to_have_count(5)
    card = profiles(page).last
    expect(card.get_by_test_id('profile-id')).to_have_value('deepseek-2')
    expect(card.get_by_test_id('profile-enabled')).not_to_be_checked()
    card.locator('.settings-advanced > summary').click()
    assert json.loads(card.get_by_test_id('profile-extra_body').input_value()) == {'thinking': {'type': 'disabled'}}
    card.get_by_test_id('profile-protocol').select_option('anthropic_messages')
    expect(card.get_by_test_id('profile-response_format')).to_have_value('prompt')
    expect(card.get_by_test_id('profile-anthropic_version')).to_be_visible()
    expect(card.get_by_test_id('profile-token_limit_field')).not_to_be_visible()
    card.get_by_test_id('profile-protocol').select_option('openai_chat')
    card.get_by_test_id('profile-response_format').select_option('json_object')
    card.get_by_test_id('profile-id').fill('my-model')
    card.get_by_test_id('profile-model').fill('synthetic-model')
    card.get_by_test_id('profile-enabled').check()
    card.get_by_test_id('profile-key').fill(SECRET)
    page.get_by_test_id('ai-default-profile').select_option('my-model')
    page.get_by_test_id('ai-enabled').check()
    first = open_profile(page)
    first.get_by_test_id('profile-key').fill('another-synthetic-value')
    page.get_by_test_id('ai-settings-save').click()
    expect(page.get_by_text('同一密钥引用填写了不同新值，请保持一致。', exact=True)).to_be_visible()
    assert not api.payloads
    first.get_by_test_id('profile-key').fill('')
    secret_not_exposed(page)
    page.get_by_test_id('ai-settings-save').click()
    expect(page.get_by_text('配置已保存 · 等待重启', exact=True)).to_be_visible()
    assert api.payloads[-1]['body']['key_updates'] == [{'ref': 'deepseek', 'value': SECRET}]
    assert all(control.input_value() == '' for control in page.get_by_test_id('profile-key').all())
    secret_not_exposed(page)
    card = open_profile(page, 4)
    expect(card.get_by_test_id('profile-key-state')).to_have_text('已配置（不会显示原值）')
    card.get_by_test_id('profile-delete').click()
    page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
    expect(profiles(page)).to_have_count(5)
    card.get_by_test_id('profile-delete').click()
    page.get_by_role('dialog').get_by_role('button', name='删除配置', exact=True).click()
    expect(profiles(page)).to_have_count(4)
    expect(page.get_by_test_id('ai-default-profile')).to_have_value('')
    page.get_by_test_id('ai-default-profile').select_option('')
    first = open_profile(page)
    first.get_by_test_id('profile-label').fill('不应恢复旧默认项')
    expect(page.get_by_test_id('ai-default-profile')).to_have_value('')
    first.get_by_test_id('profile-id').fill('renamed-deepseek')
    page.get_by_test_id('ai-default-profile').select_option('renamed-deepseek')
    first.get_by_test_id('profile-id').fill('final-deepseek')
    expect(page.get_by_test_id('ai-default-profile')).to_have_value('final-deepseek')
    page.get_by_test_id('ai-settings-save').click()
    expect(page.get_by_text('配置已保存 · 等待重启', exact=True)).to_be_visible()
    assert api.payloads[-1]['body']['key_updates'] == []
    page.set_viewport_size({'width': 390, 'height': 1000})
    expect(page.get_by_test_id('mobile-settings-link')).to_be_visible()
    first = open_profile(page)
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(evidence / 'settings-390.png'), full_page=True, animations='disabled')
    page.screenshot(path=str(evidence / 'settings-390-top.png'), full_page=False, animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    return {'status': 'passed', 'preset_protocol_adaptation': True, 'explicit_key_update_only': True,
            'passwords_cleared_after_save': True, 'delete_confirmation': True, 'default_identity_rename': True,
            'explicit_no_default_retained': True, 'shared_reference_conflict_rejected_locally': True,
            'mobile_visible_settings_entry': True, 'mobile_no_overflow': True}
