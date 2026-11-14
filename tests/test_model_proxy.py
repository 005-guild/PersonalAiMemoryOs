from app.agents import proxy


def test_windows_proxy_fallback_preserves_loopback_bypass(monkeypatch):
    monkeypatch.setattr(proxy.request,'getproxies_environment',lambda:{'no':'localhost,127.0.0.1'})
    monkeypatch.setattr(proxy,'windows_proxies',lambda:{'https':'http://127.0.0.1:17890','http':'http://127.0.0.1:17890'})
    assert proxy.model_proxy('https://api.openai.com/v1/responses')=='http://127.0.0.1:17890'
    assert proxy.model_proxy('http://127.0.0.1:11434/v1') is None
    assert proxy.model_proxy('http://localhost:6333') is None


def test_explicit_environment_proxy_and_domain_bypass_take_precedence(monkeypatch):
    def forbidden():raise AssertionError('Registry must not override an explicit environment route')
    monkeypatch.setattr(proxy,'windows_proxies',forbidden)
    monkeypatch.setattr(proxy.request,'getproxies_environment',lambda:{'https':'http://proxy.example:8080','no':'localhost'})
    assert proxy.model_proxy('https://api.openai.com/v1') is None
    monkeypatch.setattr(proxy.request,'getproxies_environment',lambda:{'no':'.openai.com'})
    assert proxy.model_proxy('https://api.openai.com/v1') is None


def test_disabled_or_invalid_registry_proxy_does_not_invent_a_route(monkeypatch):
    monkeypatch.setattr(proxy.request,'getproxies_environment',lambda:{})
    for value in ({},{'https':'file:///credentials'},{'https':'http://proxy.example?token=private'}):
        monkeypatch.setattr(proxy,'windows_proxies',lambda:value)
        assert proxy.model_proxy('https://api.openai.com/v1') is None
