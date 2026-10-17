"""Do not start providers with settings read from an interrupted file commit."""

import pytest

from app.config import Settings
from app.main import create_app


def test_default_startup_reads_settings_after_configuration_recovery(isolated_project, monkeypatch):
    dotenv = isolated_project / ".env"
    dotenv.write_text("MEMORY_OS_AI_ENABLED=true\n", encoding="utf-8")
    observed = []

    def recovered(root):
        observed.append(root)
        dotenv.write_text("MEMORY_OS_AI_ENABLED=false\n", encoding="utf-8")
        return True

    monkeypatch.setattr("app.main.recover_ai_settings", recovered)
    app = create_app()
    assert observed == [isolated_project]
    assert app.state.settings.ai_enabled is False
    assert app.state.ai_settings.describe()["active"]["enabled"] is False


def test_injected_settings_must_be_reloaded_after_recovery_changes_files(isolated_project, monkeypatch):
    settings = Settings(_env_file=None, runtime_root=isolated_project, ai_enabled=True)
    monkeypatch.setattr("app.main.recover_ai_settings", lambda root: True)
    with pytest.raises(RuntimeError, match="重新加载 Settings"):
        create_app(settings)
