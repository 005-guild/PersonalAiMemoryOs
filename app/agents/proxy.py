"""Honor an enabled Windows proxy when NO_PROXY hides urllib's registry fallback."""
from urllib import request
from urllib.parse import urlsplit


def windows_proxies():
    loader=getattr(request,'getproxies_registry',None)
    return loader() if loader else {}


def model_proxy(url):
    environment=request.getproxies_environment()
    # HTTPX already handles explicit environment proxies and their bypass rules.
    if any(environment.get(key) for key in ('http','https','all')):return None
    parsed=urlsplit(url)
    if request.proxy_bypass_environment(parsed.netloc,environment):return None
    value=windows_proxies().get(parsed.scheme)
    if not value:return None
    proxy=urlsplit(value)
    if proxy.scheme not in {'http','https'} or not proxy.hostname or proxy.query or proxy.fragment:return None
    return value
