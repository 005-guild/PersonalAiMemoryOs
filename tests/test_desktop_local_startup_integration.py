"""A dependency failure may disable RAG for this launch, never saved settings."""

import pytest

from app.config import Settings
from app.desktop import launcher, local_services


def test_local_service_success_keeps_the_original_settings(monkeypatch):
    original = Settings(_env_file=None, rag_enabled=True)
    calls = []
    monkeypatch.setattr(local_services, "start_local_services", lambda root, settings: calls.append(settings))
    assert launcher.prepare_local_rag(original.runtime_root, original) is original
    assert calls == [original]


@pytest.mark.parametrize("continue_management", [True, False])
def test_dependency_failure_requires_choice_and_preserves_saved_configuration(monkeypatch, tmp_path, continue_management):
    configuration = tmp_path / ".env"
    configuration.write_text("MEMORY_OS_RAG_ENABLED=true\n", encoding="utf-8")
    original = Settings(_env_file=configuration, runtime_root=tmp_path, rag_enabled=True)

    def unavailable(*_):
        raise local_services.LocalServicesError("本地服务尚未就绪。")

    prompts = []
    monkeypatch.setattr(local_services, "start_local_services", unavailable)
    monkeypatch.setattr(launcher, "message", lambda text, **kwargs: prompts.append((text, kwargs)) or continue_management)
    if continue_management:
        active = launcher.prepare_local_rag(tmp_path, original)
        assert not active.rag_enabled
        assert active.ai_enabled == original.ai_enabled
    else:
        with pytest.raises(launcher.DesktopPlatformError, match="已取消启动"):
            launcher.prepare_local_rag(tmp_path, original)
    assert original.rag_enabled
    assert configuration.read_text(encoding="utf-8") == "MEMORY_OS_RAG_ENABLED=true\n"
    assert prompts and prompts[0][1] == {"question": True}
