import asyncio
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from netcoop import generate, normalize, analyze, correlate

def decision(raw):
    n=normalize(raw)
    return correlate([analyze(a,n) for a in ('performance','infrastructure','connectivity')],n)

@pytest.mark.parametrize('scenario,cause',[
    ('normal','normal'),('congestion','link_congestion'),('weak_wifi','weak_wifi'),
    ('interface_fault','interface_fault'),('dns_failure','dns_dhcp_failure'),
    ('interop_legacy','link_congestion'),('device_overload','device_overload'),
    ('missing_data','insufficient_evidence'),('stale_data','insufficient_evidence'),
])
def test_expected_diagnoses(scenario,cause):
    assert decision(generate(scenario))['cause']==cause

@pytest.mark.parametrize('value',['94',True,float('nan'),float('inf'),-1,101])
def test_invalid_percentages(value):
    raw=generate('normal');raw['devices'][0]['cpu_pct']=value
    with pytest.raises(ValueError):normalize(raw)

def test_legacy_converts_units():
    n=normalize(generate('interop_legacy'))
    assert n['metrics']['latency_ms']==280
    assert n['devices'][1]['link_util_pct']==94
    assert any('legacy' in s for s in n['quality']['warnings'])

def test_no_input_mutation():
    raw=generate('congestion');before=copy.deepcopy(raw);normalize(raw);assert raw==before

@pytest.mark.parametrize('raw',[{},[],{'schema_version':'9'},generate('malformed')])
def test_malformed_rejected(raw):
    with pytest.raises(ValueError):normalize(raw)

def test_duplicate_devices():
    raw=generate('normal');raw['devices'][1]['id']=raw['devices'][0]['id']
    with pytest.raises(ValueError):normalize(raw)

def test_invalid_topology():
    raw=generate('normal');raw['links'].append(['fake','CORE_RTR_01'])
    with pytest.raises(ValueError):normalize(raw)

def test_unknown_service_not_failure():
    raw=generate('normal');raw['services']['dns']='unknown'
    assert decision(raw)['cause']=='normal'

def test_agent_failure_does_not_imply_healthy():
    assert correlate([],normalize(generate('normal')))['cause']=='insufficient_evidence'

def test_conflicting_hypotheses_abstain():
    n=normalize(generate('normal'))
    d=correlate([{'support':{'interface_fault':1,'weak_wifi':.9}}]*3,n)
    assert d['cause']=='insufficient_evidence'
    assert d['confidence']<.5

def test_mixed_fault_alternatives():
    d=decision(generate('mixed_fault'))
    assert 'interface_fault' in d['alternatives'] or d['cause']=='interface_fault'

def test_real_mcp_end_to_end():
    from engine import diagnose
    r=asyncio.run(diagnose('congestion'))
    assert r['report']['cause']=='link_congestion',r['report']
    assert len(r['report']['evidence_sources'])==3
    assert any(m['type']=='connected' and m['payload']['transport']=='stdio' for m in r['messages'])
    assert [m['sequence'] for m in r['messages']]==list(range(1,len(r['messages'])+1))

def test_mcp_invalid_input_report():
    from engine import diagnose
    r=asyncio.run(diagnose('malformed'))
    assert r['report']['status']=='error'
    assert r['report']['confidence']==0

def test_http_stream_and_history(tmp_path,monkeypatch):
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server,'DB',tmp_path/'incidents.sqlite3')
    with TestClient(server.app) as client:
        assert client.get('/').status_code==200
        assert client.post('/api/diagnose',json={'scenario':'not_real'}).status_code==422
        response=client.post('/api/diagnose/stream',json={'scenario':'weak_wifi','mode':'demo'})
        events=[json.loads(x) for x in response.text.splitlines()]
        assert events[-1]['event']=='complete'
        r=events[-1]['data']['report']
        assert r['cause']=='weak_wifi'
        assert client.get('/api/incidents/'+r['incident_id']).json()['report']==r
        assert len(client.get('/api/incidents').json())==1
        assert client.get('/api/incidents/not-found').status_code==404

def test_gemini_tool_loop_preserves_signature(monkeypatch):
    import engine
    monkeypatch.setenv('GEMINI_API_KEY','test-key-not-real')
    requests=[];calls=[]
    class Response:
        def __init__(self,data):self.data=data
        def raise_for_status(self):pass
        def json(self):return self.data
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            requests.append(copy.deepcopy(kwargs['json']))
            part={'functionCall':{'name':'inspect_device','args':{'device_id':'CORE_RTR_01'},'id':'call-1'},'thoughtSignature':'opaque-signature'} if len(requests)==1 else {'text':'Evidence suggests congestion. Verify queue behavior.'}
            return Response({'candidates':[{'content':{'role':'model','parts':[part]}}]})
    monkeypatch.setattr(engine.httpx,'AsyncClient',Client)
    async def call(name,args,sender):calls.append((name,args,sender));return {'device':{'id':'CORE_RTR_01'}}
    async def emit(*args):pass
    r=asyncio.run(engine.investigate(normalize(generate('congestion')),{'cause':'link_congestion'},call,emit))
    assert r['status']=='connected' and r['tool_calls']==1
    assert calls[0][0]=='inspect_device'
    assert requests[1]['contents'][1]['parts'][0]['thoughtSignature']=='opaque-signature'
    assert requests[1]['contents'][2]['parts'][0]['functionResponse']['id']=='call-1'

def test_gemini_failure_falls_back(monkeypatch):
    import engine
    monkeypatch.setenv('GEMINI_API_KEY','test-key-not-real')
    class BadClient:
        def __init__(self,**kwargs):raise RuntimeError('secret error detail')
    monkeypatch.setattr(engine.httpx,'AsyncClient',BadClient)
    async def noop(*args):pass
    r=asyncio.run(engine.investigate({}, {}, noop, noop))
    assert r['status']=='unavailable'
    assert 'secret' not in r['summary']


def test_import_python_generator_and_errors(tmp_path):
    from importer import extract
    good = "def generate():\n    return " + repr(generate('congestion')) + "\n"
    raw, how = extract('t.py', good)
    assert normalize(raw)['metrics']['latency_ms'] == 280 and 'generate' in how
    with pytest.raises(ValueError, match='syntax'):
        extract('bad.py', 'def x(:')
    with pytest.raises(ValueError, match='No telemetry'):
        extract('none.py', 'print("hi")')
    with pytest.raises(ValueError, match='only enabled'):
        extract('t.py', good, allow_python=False)
    with pytest.raises(ValueError, match='JSON'):
        extract('t.json', 'hello')


def test_import_endpoint_validates_immediately():
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as client:
        ok = client.post('/api/import', json={'filename': 't.json', 'content': json.dumps(generate('weak_wifi'))})
        assert ok.status_code == 200 and ok.json()['normalized']['quality']['coverage'] > 0
        bad = client.post('/api/import', json={'filename': 't.json', 'content': json.dumps(generate('malformed'))})
        assert bad.status_code == 422


def test_import_adapts_schema_variants_and_explains_failures():
    from importer import extract
    raw = generate('congestion'); raw.pop('schema_version')
    fixed, how = extract('t.json', json.dumps(raw))
    assert normalize(fixed)['metrics']['latency_ms'] == 280 and 'assumed 1.0' in how
    raw['schema_version'] = 'netcoop.telemetry/1.0'
    assert normalize(extract('t.json', json.dumps(raw))[0])['quality']['coverage'] > 0
    raw['schema_version'] = '2.0'
    with pytest.raises(ValueError, match='Top-level keys found'):
        extract('t.json', json.dumps(raw))


FLAT_FILE = json.dumps({
    'normal': {'timestamp': '2026-11-01T04:45:00.123456+05:30', 'device_id': 'SW_CAMPUS_7', 'status': 'Healthy',
               'metrics': {'cpu_utilization_pct': 22.4, 'link_utilization_pct': 34.1, 'packet_loss_pct': 0.0,
                           'latency_ms': 11.8, 'jitter_ms': 2.6, 'queue_drops': 0}},
    'hardware_failure': {'timestamp': '2026-11-01T04:45:00+05:30', 'device_id': 'SW_CAMPUS_9', 'status': 'Critical',
                         'metrics': {'cpu_utilization_pct': 99.9, 'link_utilization_pct': 100.0, 'packet_loss_pct': 24.6,
                                     'latency_ms': 841.1, 'queue_drops': 11204, 'interface_errors': 273, 'mystery': 1}},
})


def test_import_single_device_named_snapshots():
    from importer import extract_many
    items, how = extract_many('allD.json', FLAT_FILE)
    assert [i[0] for i in items] == ['normal', 'hardware_failure'] and '2 named snapshots' in how
    name, t, notes = items[1]
    d = t['devices'][0]
    assert (d['id'], d['type'], d['status'], d['cpu_pct'], d['if_errors']) == ('SW_CAMPUS_9', 'switch', 'degraded', 99.9, 273)
    assert t['metrics']['latency_ms'] == 841.1 and isinstance(t['timestamp'], float)
    assert any('mystery' in n for n in notes)
    assert normalize(t)['quality']['coverage'] > 0


def test_import_endpoint_stale_prompt_and_replay():
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as client:
        r = client.post('/api/import', json={'filename': 'allD.json', 'content': FLAT_FILE}).json()
        assert len(r['datasets']) == 2 and r['stale']
        r = client.post('/api/import', json={'filename': 'allD.json', 'content': FLAT_FILE, 'replay': True}).json()
        assert r['stale'] is None and not r['datasets'][0]['normalized']['quality']['stale']
        rep = client.post('/api/diagnose', json={'telemetry': r['datasets'][1]['telemetry']}).json()['report']
        assert any('Recorded snapshot' in x for x in rep['limitations'])
        bad = client.post('/api/import', json={'filename': 'x.json', 'content': json.dumps({'a': {'device_id': 'X', 'timestamp': 'yesterday', 'metrics': {}}})})
        assert bad.status_code == 422 and 'timestamp' in bad.json()['detail']


GENERATOR_SCRIPT = '''
import random
def generate_telemetry(fault_type="normal"):
    d = {"timestamp": 1793460000, "device_id": "SW_1", "metrics": {}}
    if fault_type == "latency_spike":
        d["metrics"] = {"latency_ms": 250, "jitter_ms": 40}
        d["status"] = "Warning"
    elif fault_type == "hardware_failure":
        d["metrics"] = {"cpu_utilization_pct": 99.9, "interface_errors": 300}
        d["status"] = "Critical"
    else:
        d["metrics"] = {"latency_ms": 10}
        d["status"] = "Healthy"
    return d
print("noise before data")
'''


def test_import_python_generator_with_scenario_argument():
    from importer import extract_many
    items, how = extract_many('gen.py', GENERATOR_SCRIPT)
    assert [i[0] for i in items] == ['normal', 'latency_spike', 'hardware_failure']
    assert 'generate_telemetry' in how
    assert [i[1]['devices'][0]['status'] for i in items] == ['up', 'degraded', 'degraded']
    assert items[2][1]['devices'][0]['if_errors'] == 300


def test_import_python_any_zero_argument_function():
    from importer import extract_many
    src = 'def build_snapshot():\n    return {"schema_version": "1.0", "timestamp": 1, "devices": [{"id": "A", "type": "switch", "status": "up"}], "metrics": {}}\n'
    items, how = extract_many('x.py', src)
    assert 'build_snapshot' in how and items[0][1]['devices'][0]['id'] == 'A'


PROVIDER_SOURCE = '''
import random
print("module-level noise must not break the MCP stream")
def generate_telemetry(fault_type="normal"):
    d = {"timestamp": __import__("time").time(), "device_id": "SW_T", "metrics": {"latency_ms": 10.0, "packet_loss_pct": 0.0}, "status": "Healthy"}
    if fault_type == "latency_spike":
        d["metrics"]["latency_ms"] = 300.0
        d["status"] = "Warning"
    elif fault_type == "hardware_failure":
        d["metrics"].update(cpu_utilization_pct=99.9, interface_errors=400)
        d["status"] = "Critical"
    return d
'''


@pytest.fixture
def provider_file(tmp_path, monkeypatch):
    f = tmp_path / 'my_provider.py'
    f.write_text(PROVIDER_SOURCE)
    monkeypatch.setenv('NETCOOP_PROVIDER', str(f))
    return f


def test_provider_discovers_scenarios_and_fetches(provider_file):
    import provider
    info = provider.inspect_provider()
    assert info['available'] and info['scenarios'] == ['normal', 'latency_spike', 'hardware_failure']
    t = provider.fetch('provider:latency_spike')
    assert t['metrics']['latency_ms'] == 300.0 and t['devices'][0]['status'] == 'degraded'
    assert t['provider']['function'] == 'generate_telemetry' and normalize(t)['quality']['stale'] is False


def test_provider_runs_through_mcp_on_every_investigation(provider_file):
    from engine import diagnose
    r = asyncio.run(diagnose('provider:hardware_failure'))
    rep = r['report']
    assert rep['status'] in ('diagnosed', 'insufficient_evidence') and rep['evidence_sources'] == ['performance', 'infrastructure', 'connectivity']
    src = [m for m in r['messages'] if m['type'] == 'telemetry_source']
    assert len(src) == 1 and src[0]['payload']['scenario'] == 'hardware_failure'
    assert any('my_provider.py' in x for x in rep['limitations'])
    assert any(e['metric'] == 'interface_errors' for e in rep['supporting_evidence'])


def test_provider_failures_are_explained(tmp_path, monkeypatch):
    from engine import diagnose
    import provider
    bad = tmp_path / 'broken.py'
    bad.write_text('def generate_telemetry(kind="a"):\n    if kind == "a":\n        raise RuntimeError("sensor offline")\n    if kind == "b":\n        return {}\n')
    monkeypatch.setenv('NETCOOP_PROVIDER', str(bad))
    r = asyncio.run(diagnose('provider:a'))
    assert r['report']['status'] == 'error' and 'sensor offline' in r['report']['limitations'][0]
    slow = tmp_path / 'slow.py'
    slow.write_text('import time\ndef generate_telemetry(kind="a"):\n    if kind == "a" or kind == "b":\n        time.sleep(30)\n')
    monkeypatch.setenv('NETCOOP_PROVIDER', str(slow))
    monkeypatch.setenv('NETCOOP_PROVIDER_TIMEOUT', '1')
    with pytest.raises(ValueError, match='did not finish'):
        provider.fetch('provider:a')
    monkeypatch.setenv('NETCOOP_PROVIDER', str(tmp_path / 'missing.py'))
    assert provider.inspect_provider()['available'] is False


def test_provider_http_endpoints(provider_file):
    import server
    from fastapi.testclient import TestClient
    with TestClient(server.app) as client:
        info = client.get('/api/provider').json()
        assert info['available'] and 'hardware_failure' in info['scenarios']
        assert client.get('/api/telemetry/provider:normal').json()['provider']['scenario'] == 'normal'
        assert client.post('/api/diagnose', json={'scenario': 'provider:nope'}).status_code == 422
        events = [json.loads(x) for x in client.post('/api/diagnose/stream', json={'scenario': 'provider:latency_spike'}).text.splitlines()]
        assert any(e['event'] == 'message' and e['data']['type'] == 'telemetry_source' for e in events)
        assert events[-1]['event'] == 'complete'
