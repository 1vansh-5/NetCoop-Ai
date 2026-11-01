import asyncio
import json
import pytest
import groq_decision
from netcoop import generate, normalize


async def noop(*args):
    pass


def mock_api(monkeypatch, value):
    monkeypatch.setenv('GROQ_API_KEY', 'test-placeholder')
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'choices': [{'message': {'content': json.dumps(value)}}]}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            assert url == 'https://api.groq.com/openai/v1/chat/completions'
            assert kwargs['json']['response_format']['type'] == 'json_object'
            return Response()
    monkeypatch.setattr(groq_decision.httpx, 'AsyncClient', Client)


VALID = {'cause': 'device_overload', 'confidence': .81, 'summary': 'CPU is saturated; verify the device.', 'alternatives': ['link_congestion']}


def test_groq_decides_final_report(monkeypatch):
    import engine
    mock_api(monkeypatch, VALID)
    r = asyncio.run(engine.diagnose('congestion', llm_provider='groq'))['report']
    assert r['cause'] == 'device_overload'
    assert r['specialist_baseline']['cause'] == 'link_congestion'
    assert r['decision_source'] == 'groq'
    assert r['confidence'] == .81
    assert r['recommended_actions']


@pytest.mark.parametrize('value', [dict(VALID, cause='made_up'), dict(VALID, confidence=5), dict(VALID, confidence=True), dict(VALID, summary=''), dict(VALID, alternatives=['made_up'])])
def test_invalid_ai_falls_back(monkeypatch, value):
    mock_api(monkeypatch, value)
    r = asyncio.run(groq_decision.decide(normalize(generate()), {}, [{}, {}, {}], noop))
    assert r['status'] == 'unavailable'
    assert 'decision' not in r
    assert 'test-placeholder' not in str(r)


def test_stale_ai_is_guarded(monkeypatch):
    mock_api(monkeypatch, VALID)
    r = asyncio.run(groq_decision.decide(normalize(generate('stale_data')), {}, [{}, {}, {}], noop))
    assert r['decision']['cause'] == 'insufficient_evidence'
    assert r['decision']['confidence'] <= .49


def test_groq_missing_key_http(monkeypatch, tmp_path):
    import server
    from fastapi.testclient import TestClient
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.setattr(server, 'DB', tmp_path/'incidents.sqlite3')
    with TestClient(server.app) as client:
        assert client.get('/api/health').json()['groq_configured'] is False
        r = client.post('/api/diagnose', json={'scenario':'provider:normal','mode':'groq'}).json()['report']
        assert r['status'] != 'error'
        assert r['decision_source'] == 'specialist_fallback'
        assert r['ai']['status'] == 'offline'
