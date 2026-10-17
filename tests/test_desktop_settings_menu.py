"""Desktop settings navigation keeps the existing unsaved-edit route guard."""

from app.desktop.launcher import open_ai_settings


def test_desktop_settings_uses_hash_navigation_without_reloading_the_page():
    scripts = []

    class Window:
        def evaluate_js(self, value):
            scripts.append(value)

        def load_url(self, value):
            raise AssertionError("Settings must retain the active dirty-form router.")

    open_ai_settings(Window())
    assert scripts == ["window.location.hash = '#/settings'; void 0;"]


def test_unready_workbench_message_does_not_echo_renderer_errors(monkeypatch, caplog):
    messages = []
    monkeypatch.setattr("app.desktop.launcher.message", messages.append)

    class Window:
        def evaluate_js(self, value):
            raise RuntimeError("SENSITIVE_RENDERER_TEXT")

    open_ai_settings(Window())
    assert messages == ["工作台尚未加载完成，请稍后再次打开设置。"]
    assert "SENSITIVE_RENDERER_TEXT" not in caplog.text
