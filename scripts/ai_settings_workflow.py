"""Actual WebView2 configuration editing; no provider requests are initiated."""

import re

from playwright.sync_api import expect

from ai_settings_verification import secret_absent

PROFILE_ID = "desktop_validation"


def assert_password_privacy(page, secret):
    assert secret not in page.locator("body").inner_text()
    assert secret not in page.content()
    assert secret not in page.url
    values = page.evaluate("({local: {...localStorage}, session: {...sessionStorage}})")
    secret_absent(values, secret)
    for password in page.get_by_test_id("profile-key").all():
        expect(password).to_have_attribute("type", "password")
        expect(password).to_have_value("")


def save_settings_in_browser(page, app, model_url, secret, evidence):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.get_by_test_id("desktop-settings-link").click()
    expect(page).to_have_url(re.compile(r"#/settings$"))
    expect(page.get_by_test_id("ai-settings-save")).to_be_enabled()
    expect(page.get_by_text("当前 AI 已关闭", exact=True)).to_be_visible()
    page.get_by_label("新配置模板", exact=True).select_option("compatible")
    page.get_by_test_id("ai-add-profile").click()
    profile = page.get_by_test_id("ai-profile").last
    for name, value in {"id": PROFILE_ID, "label": "便携设置验收", "model": "synthetic-settings-model",
                        "base_url": model_url, "api_key_ref": PROFILE_ID,
                        "max_output_tokens": "64", "timeout_seconds": "2"}.items():
        profile.get_by_test_id(f"profile-{name}").fill(value)
    profile.get_by_test_id("profile-auth").select_option("bearer")
    profile.get_by_test_id("profile-enabled").check()
    profile.get_by_test_id("profile-key").fill(secret)
    page.get_by_test_id("ai-enabled").check()
    page.get_by_test_id("ai-default-profile").select_option(PROFILE_ID)
    with page.expect_response(lambda response: response.request.method == "PUT"
                              and response.url.endswith("/api/v1/settings/ai")) as response_event:
        page.get_by_test_id("ai-settings-save").click()
    response = response_event.value
    assert response.status == 200
    assert response.headers.get("cache-control") == "no-store"
    saved = response.json()
    secret_absent(saved, secret)
    assert saved["enabled"] is True and saved["default_profile"] == PROFILE_ID
    assert saved["active"]["enabled"] is False and saved["restart_required"] is True
    expect(page.get_by_text("配置已保存 · 等待重启", exact=True)).to_be_visible()
    expect(page.get_by_text("当前 AI 已关闭", exact=True)).to_be_visible()
    expect(page.get_by_test_id("ai-settings-save")).to_be_enabled()
    assert_password_privacy(page, secret)
    assert not page.evaluate("window.memoryOsHasUnsavedChanges()")
    active = app.request("GET", "/api/v1/ai/profiles")
    assert active["enabled"] is False and PROFILE_ID not in {item["id"] for item in active["items"]}
    assert not errors
    page.screenshot(path=str(evidence / "settings-saved-pending-restart.png"), full_page=True)
    return {"status": "passed", "settings_saved_once": True, "password_not_echoed": True,
            "local_session_storage_excludes_key": True, "no_hot_apply": True, "page_errors": errors}


def verify_settings_after_restart(page, app, secret, evidence):
    page.get_by_test_id("desktop-settings-link").click()
    expect(page.get_by_test_id("ai-settings-save")).to_be_enabled()
    expect(page.get_by_text("当前 AI 已开启", exact=True)).to_be_visible()
    expect(page.get_by_test_id("ai-default-profile")).to_have_value(PROFILE_ID)
    expect(page.get_by_text("启动配置已加载", exact=True)).to_be_visible()
    snapshot = app.request("GET", "/api/v1/settings/ai")
    secret_absent(snapshot, secret)
    assert snapshot["active"] == {"enabled": True, "default_profile": PROFILE_ID}
    assert snapshot["restart_required"] is False
    assert next(key for key in snapshot["keys"] if key["ref"] == PROFILE_ID)["configured"] is True
    # Inputs use DOM properties, so identify the card without relying on value attributes.
    selected = next(card for card in page.get_by_test_id("ai-profile").all()
                    if card.get_by_test_id("profile-id").input_value() == PROFILE_ID)
    selected.locator("summary").first.click()
    expect(selected.get_by_test_id("profile-key-state")).to_have_text("已配置（不会显示原值）")
    assert_password_privacy(page, secret)
    active = app.request("GET", "/api/v1/ai/profiles")
    assert active["enabled"] is True and active["default_profile"] == PROFILE_ID
    profile = next(item for item in active["items"] if item["id"] == PROFILE_ID)
    assert profile["enabled"] and profile["configured"]
    page.screenshot(path=str(evidence / "settings-reloaded-after-restart.png"), full_page=True)
    return {"status": "passed", "restart_loads_profile_and_key": True,
            "configured_not_connectivity_tested": True, "passwords_empty_after_restart": True}
