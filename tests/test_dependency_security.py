"""Exercise the patched TLS store and bounded trace-context rejection locally."""

import ssl
from types import SimpleNamespace

import certifi
from opentelemetry import trace
from opentelemetry.trace.propagation import tracecontext


def test_http_client_ca_store_excludes_compromised_emsign_ecc_root():
    context = ssl.create_default_context(cafile=certifi.where())
    names = {value for certificate in context.get_ca_certs()
             for row in certificate['subject'] for key, value in row if key == 'commonName'}
    assert 'emSign ECC Root CA - G3' not in names


def test_large_newline_traceparent_is_rejected_before_regex_work(monkeypatch):
    # A canary proves rejection happens before regex evaluation and avoids
    # conflating interpreter startup or machine load with parser performance.
    def unexpected_search(*args):
        raise AssertionError('Oversized traceparent reached regex evaluation')

    original_re = tracecontext.re
    monkeypatch.setattr(tracecontext, 're', SimpleNamespace(search=unexpected_search))
    prefix = '00-' + '1' * 32 + '-' + '2' * 16 + '-01'
    context = tracecontext.TraceContextTextMapPropagator().extract({'traceparent': prefix + ' ' * 100000 + '\n'})
    assert not trace.get_current_span(context).get_span_context().is_valid
    monkeypatch.setattr(tracecontext, 're', original_re)
    context = tracecontext.TraceContextTextMapPropagator().extract({'traceparent': prefix})
    assert trace.get_current_span(context).get_span_context().is_valid
