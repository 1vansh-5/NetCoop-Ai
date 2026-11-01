"""Validated telemetry and independent, deterministic diagnostic specialists."""
import copy
import math
import time
from legacy_rules import generate as base_generate, normalize as base_normalize
from legacy_rules import performance_agent, infrastructure_agent as base_infra, connectivity_agent as base_conn, ACTIONS

SCENARIOS = ['normal', 'congestion', 'weak_wifi', 'interface_fault', 'dns_failure', 'interop_legacy', 'mixed_fault', 'missing_data', 'stale_data', 'device_overload', 'malformed']
LABELS = {'normal': 'No fault detected in available telemetry', 'link_congestion': 'Likely uplink congestion', 'weak_wifi': 'Likely weak wireless signal', 'interface_fault': 'Likely Ethernet interface fault', 'dns_dhcp_failure': 'Likely DNS or DHCP failure', 'device_overload': 'Likely device resource overload', 'insufficient_evidence': 'Insufficient evidence for a reliable diagnosis'}

def generate(scenario='normal', seed=7):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown scenario')
    raw = base_generate(scenario, seed)
    if scenario == 'mixed_fault':
        raw = base_generate('congestion', seed)
        raw['devices'][2].update(if_errors=830, status='degraded')
        raw['metrics'].update(latency_ms=95, jitter_ms=30, packet_loss_pct=6.5)
    if scenario == 'missing_data':
        raw = {'schema_version': '1.0', 'devices': [{'id': 'UNKNOWN_01', 'type': 'switch'}], 'metrics': {}}
    if scenario == 'stale_data':
        raw = base_generate('congestion', seed)
        raw['timestamp'] = time.time() - 7200
    if scenario == 'device_overload':
        raw['devices'][0].update(cpu_pct=96, mem_pct=94)
    return raw

def number(value, field, low=None, high=None):
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{field} must be a finite number')
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(f'{field} is outside its allowed range')

def normalize(raw):
    if not isinstance(raw, dict):
        raise ValueError('Telemetry must be an object')
    version = raw.get('schema_version', raw.get('schema'))
    if version not in ('1.0', '0.9'):
        raise ValueError('Unsupported schema: expected 1.0 or legacy 0.9')
    legacy = version == '0.9'
    devices = raw.get('nodes' if legacy else 'devices')
    metrics = raw.get('kpi' if legacy else 'metrics')
    if not isinstance(devices, list) or not 1 <= len(devices) <= 200 or not isinstance(metrics, dict):
        raise ValueError('Expected 1–200 devices and a metrics object')
    numeric_keys = {'cpu_pct','mem_pct','if_errors','queue_drops','link_util_pct','signal_dbm','retransmit_pct','cpu','util','drops','errors','rssi','mem'}
    for d in devices:
        if not isinstance(d, dict):
            raise ValueError('Each device must be an object')
        for k in numeric_keys & d.keys():
            number(d[k], k)
    for k,v in metrics.items():
        number(v, k, 0)
    n, warnings = base_normalize(copy.deepcopy(raw))
    ids = []
    for d in n['devices']:
        if not isinstance(d['id'], str) or not 1 <= len(d['id']) <= 100:
            raise ValueError('Device ID must be a string of 1–100 characters')
        ids.append(d['id'])
        if d['status'] not in ('up','down','degraded','unknown'):
            raise ValueError('Unsupported device status')
        for k in ('cpu_pct','mem_pct','link_util_pct','retransmit_pct'):
            number(d[k], k, 0, 100)
        for k in ('if_errors','queue_drops'):
            number(d[k], k, 0)
        number(d['signal_dbm'], 'signal_dbm', -150, 0)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('Device IDs must be present and unique')
    number(n['metrics']['packet_loss_pct'], 'packet_loss_pct', 0, 100)
    if not isinstance(n['links'], list):
        raise ValueError('links must be a list')
    for edge in n['links']:
        if not isinstance(edge, list) or len(edge) != 2 or any(x not in ids for x in edge):
            raise ValueError('Each link must reference two existing device IDs')
    if not isinstance(n['services'], dict) or any(k not in ('dns','dhcp') or v not in ('ok','fail','unknown') for k,v in n['services'].items()):
        raise ValueError('Services must use dns/dhcp with ok/fail/unknown')
    fields = list(n['metrics'].values()) + [d[k] for d in n['devices'] for k in ('cpu_pct','mem_pct','if_errors','queue_drops','link_util_pct')]
    coverage = sum(v is not None for v in fields) / len(fields)
    ts = raw.get('timestamp', raw.get('ts'))
    number(ts, 'timestamp', 0)
    stale = ts is None or time.time() - ts > 300 or ts > time.time() + 60
    if stale:
        warnings.append('Timestamp missing, stale (>5 minutes), or in the future; collect fresh telemetry.')
    if coverage < .8:
        warnings.append(f'Only {coverage:.0%} of core measurement fields are available.')
    n['quality'] = {'coverage': round(coverage, 3), 'stale': stale, 'warnings': warnings}
    n['schema_version'] = '1.0'
    return n

def infrastructure_agent(n):
    f,s = base_infra(n)
    for d in n['devices']:
        if (d['mem_pct'] or 0) > 90:
            f.append(dict(signal='mem_pct',value=d['mem_pct'],unit='%',severity=.8,interpretation='Memory pressure',device=d['id']))
            s['device_overload'] = s.get('device_overload',0) + .5
    return f,s

def connectivity_agent(n):
    clean = copy.deepcopy(n)
    clean['services'] = {k:v for k,v in n['services'].items() if v != 'unknown'}
    f,s = base_conn(clean)
    for d in n['devices']:
        if d['status'] == 'down':
            peers = [b if a == d['id'] else a for a,b in n['links'] if d['id'] in (a,b)]
            f.append(dict(signal='adjacency',value=len(peers),unit='neighbors',severity=.9,interpretation='Down device may disrupt adjacent devices: ' + ', '.join(peers),device=d['id']))
            s['interface_fault'] = s.get('interface_fault',0) + .5
    return f,s

AGENTS = {'performance': performance_agent, 'infrastructure': infrastructure_agent, 'connectivity': connectivity_agent}

def analyze(agent, telemetry):
    if agent not in AGENTS:
        raise ValueError('Unknown specialist')
    findings, support = AGENTS[agent](telemetry)
    return {'agent': agent, 'findings': findings, 'support': support}

def correlate(results, telemetry):
    scores = {}
    for r in results:
        for cause, weight in r['support'].items():
            scores[cause] = round(scores.get(cause,0) + weight, 3)
    ranked = sorted(scores, key=scores.get, reverse=True)
    top = scores[ranked[0]] if ranked else 0
    second = scores[ranked[1]] if len(ranked)>1 else 0
    quality = telemetry['quality']
    coverage = quality['coverage'] * len(results)/3
    conflict = bool(second and top-second < .35)
    cause = ranked[0] if ranked else 'normal'
    conf = (.5*top/(top+second) + .5*min(top/1.2,1)) if top else .9
    conf *= coverage * (.5 if quality['stale'] else 1)
    if coverage < .65 or quality['stale'] or (top and top < .4) or conflict:
        cause = 'insufficient_evidence'
        conf = min(conf,.49)
    return {'cause':cause,'confidence':round(conf,2),'scores':scores,'alternatives':ranked if cause=='insufficient_evidence' else ranked[1:], 'conflict':conflict}

def runbook(cause):
    return {'cause':cause, 'actions':ACTIONS.get(cause,['Collect fresh, complete telemetry and verify competing hypotheses.']), 'execution':'Recommendations only; no network changes are executed.'}
