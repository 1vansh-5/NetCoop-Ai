"""Extract telemetry from an uploaded .json or .py file.

.json files are parsed directly. .py files are handled in two steps:

1. Safe path: parse the source with `ast` and look for a plain dict literal that
   looks like telemetry (no code is executed).
2. Execution path: run the script in a separate, isolated Python process with a
   timeout, an empty environment (no API keys) and a throw-away working folder,
   then collect the telemetry it exposes. This is NOT a security sandbox, so the
   server only enables it for local requests (see server.py).

A telemetry-producing script can expose its data in any of these ways:
  * a variable such as TELEMETRY / telemetry / DATA / data (dict or JSON string)
  * a zero-argument function such as generate() / get_telemetry() / main()
  * printing a JSON object to stdout when run as a script
"""
import ast
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 250_000
TIMEOUT_SECONDS = 10

HARNESS = r'''
import contextlib, inspect, io, json, runpy, sys
path, out, root = sys.argv[1], sys.argv[2], sys.argv[3]
OPTIONS = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
sys.path.append(root)  # lets a script do: from netcoop import generate
VARS = ['TELEMETRY', 'telemetry', 'DATA', 'data', 'RAW', 'raw', 'SAMPLE', 'sample', 'PAYLOAD', 'payload']
FUNCS = ['generate', 'get_telemetry', 'telemetry', 'build_telemetry', 'make_telemetry', 'collect', 'get_data', 'main']

def looks(d):
    if not isinstance(d, dict) or not d:
        return False
    if {'schema_version', 'schema', 'devices', 'nodes'} & d.keys() or isinstance(d.get('metrics'), dict):
        return True
    return all(isinstance(v, dict) and (isinstance(v.get('metrics'), dict) or {'schema_version', 'schema', 'devices', 'nodes'} & v.keys()) for v in d.values())

def coerce(v):
    if isinstance(v, (str, bytes)):
        try:
            v = json.loads(v)
        except Exception:
            return None
    return v if looks(v) else None

def done(obj, how):
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'ok': True, 'telemetry': obj, 'how': how}, f)
    sys.exit(0)

def fail(msg):
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'ok': False, 'error': msg}, f)
    sys.exit(0)

def zero_arg(fn):
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    return all(p.default is not p.empty or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in sig.parameters.values())

buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        ns = runpy.run_path(path, run_name='telemetry_import')
except SystemExit:
    ns = {}
except BaseException as exc:
    fail(f'The script raised {type(exc).__name__}: {str(exc)[:300]}')

for fname, opts in OPTIONS.items():
    fn = ns.get(fname)
    if not callable(fn):
        continue
    found = {}
    for opt in opts:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                value = fn(opt)
        except BaseException as exc:
            fail(f'{fname}({opt!r}) raised {type(exc).__name__}: {str(exc)[:300]}')
        if coerce(value) is not None:
            found[str(opt)] = coerce(value)
    if found:
        done(found if len(found) > 1 else next(iter(found.values())), f'function {fname}() called with {len(found)} scenario(s)')

for name in VARS:
    if name in ns and coerce(ns[name]) is not None:
        done(coerce(ns[name]), f'variable {name}')
for name, value in ns.items():
    if not name.startswith('_') and isinstance(value, dict) and looks(value):
        done(value, f'variable {name}')
for name in FUNCS:
    fn = ns.get(name)
    if callable(fn) and zero_arg(fn):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                value = fn()
        except BaseException as exc:
            fail(f'{name}() raised {type(exc).__name__}: {str(exc)[:300]}')
        if coerce(value) is not None:
            done(coerce(value), f'function {name}()')

for name, fn in list(ns.items()):
    if name.startswith('_') or name in FUNCS or not inspect.isfunction(fn) or fn.__module__ != 'telemetry_import' or not zero_arg(fn):
        continue
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            value = fn()
    except BaseException:
        continue
    if coerce(value) is not None:
        done(coerce(value), f'function {name}()')

# Last resort: run as a normal script and read a JSON object from its output.
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        runpy.run_path(path, run_name='__main__')
except SystemExit:
    pass
except BaseException as exc:
    fail(f'The script raised {type(exc).__name__}: {str(exc)[:300]}')
text, decoder, pos = buf.getvalue(), json.JSONDecoder(), 0
while True:
    start = text.find('{', pos)
    if start < 0:
        break
    try:
        obj, end = decoder.raw_decode(text, start)
    except ValueError:
        pos = start + 1
        continue
    if looks(obj):
        done(obj, 'script output')
    pos = end
fail('No telemetry found. Expose a TELEMETRY dict, a zero-argument function such as generate(), or print a JSON object.')
'''

SCHEMA_KEYS = {'schema_version', 'schema', 'devices', 'nodes'}


def is_flat_record(d):
    """One device per record: {device_id, metrics:{...}, status, timestamp}."""
    return isinstance(d, dict) and isinstance(d.get('metrics'), dict) and not (SCHEMA_KEYS & d.keys())


def is_container(d):
    """{"name": record, "name2": record, ...}: several named snapshots in one file."""
    return (isinstance(d, dict) and d and not (SCHEMA_KEYS | {'metrics'}) & d.keys()
            and all(isinstance(v, dict) and (is_flat_record(v) or SCHEMA_KEYS & v.keys()) for v in d.values()))


DEVICE_FIELDS = {'cpu_pct': ('cpu_utilization_pct', 'cpu_pct', 'cpu_percent'),
                 'mem_pct': ('memory_utilization_pct', 'mem_utilization_pct', 'mem_pct', 'memory_pct'),
                 'link_util_pct': ('link_utilization_pct', 'link_util_pct', 'bandwidth_utilization_pct'),
                 'if_errors': ('interface_errors', 'if_errors', 'crc_errors'),
                 'queue_drops': ('queue_drops', 'drops'),
                 'signal_dbm': ('signal_dbm', 'rssi'),
                 'retransmit_pct': ('retransmit_pct', 'retransmissions_pct')}
NETWORK_FIELDS = ('latency_ms', 'jitter_ms', 'packet_loss_pct', 'throughput_mbps', 'bandwidth_mbps')
STATUS = {'healthy': 'up', 'ok': 'up', 'up': 'up', 'normal': 'up', 'warning': 'degraded', 'degraded': 'degraded',
          'critical': 'degraded', 'minor': 'degraded', 'major': 'degraded', 'down': 'down', 'failed': 'down', 'offline': 'down'}


def _timestamp(value):
    if value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip().replace('Z', '+00:00')).timestamp()
        except ValueError:
            pass
    raise ValueError(f'Could not read the timestamp {value!r}. Use Unix seconds or an ISO 8601 date such as 2026-11-01T04:45:00+05:30.')


def convert_flat(rec, name=None):
    """Convert a one-device record to schema 1.0. Returns (telemetry, notes)."""
    notes = ['Converted a single-device record to schema 1.0; its metrics are treated as network-wide measurements.']
    metrics = rec['metrics']
    device_id = str(rec.get('device_id') or rec.get('id') or rec.get('device') or name or 'DEVICE_1')
    upper = device_id.upper()
    kind = next((t for prefix, t in (('SW', 'switch'), ('RTR', 'router'), ('RT', 'router'), ('AP', 'ap'), ('WAP', 'ap'), ('FW', 'firewall')) if upper.startswith(prefix)), 'unknown')
    status_text = str(rec.get('status', 'unknown')).strip().lower()
    status = STATUS.get(status_text, 'unknown')
    if rec.get('status') is not None:
        notes.append(f"Status {rec['status']!r} mapped to {status!r}.")
    device, used = {'id': device_id, 'type': kind, 'status': status}, set()
    for target, names in DEVICE_FIELDS.items():
        for n in names:
            if n in metrics:
                device[target] = metrics[n]
                used.add(n)
                break
    net = {k: metrics[k] for k in NETWORK_FIELDS if k in metrics}
    used |= set(net)
    ignored = sorted(set(metrics) - used)
    if ignored:
        notes.append('Ignored unrecognised metrics: ' + ', '.join(ignored) + '.')
    out = {'schema_version': '1.0', 'devices': [device], 'links': [], 'metrics': net,
           'services': rec['services'] if isinstance(rec.get('services'), dict) else {}}
    stamp = rec.get('timestamp', rec.get('ts'))
    if stamp is not None:
        out['timestamp'] = _timestamp(stamp)
        out['recorded_at'] = str(stamp)
    return out, notes


def _literal_telemetry(tree):
    """Find a telemetry-looking dict literal without executing anything."""
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                continue
            if isinstance(value, dict) and (({'schema_version', 'schema'} & value.keys()) or is_flat_record(value) or is_container(value)):
                return value
    return None


def _scenario_options(tree):
    """Find functions like f(kind="normal") that branch on `kind == "x"`; return {name: [values]}."""
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name.startswith('_') or not node.args.args:
            continue
        args, defaults = node.args.args, node.args.defaults
        if len(args) - len(defaults) > 1:
            continue
        first, values = args[0].arg, []
        if len(defaults) == len(args) and isinstance(defaults[0], ast.Constant) and isinstance(defaults[0].value, str):
            values.append(defaults[0].value)
        for sub in ast.walk(node):
            if isinstance(sub, ast.Compare) and isinstance(sub.left, ast.Name) and sub.left.id == first:
                for op, comp in zip(sub.ops, sub.comparators):
                    if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        values.append(comp.value)
                    elif isinstance(op, ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                        values += [c.value for c in comp.elts if isinstance(c, ast.Constant) and isinstance(c.value, str)]
        values = list(dict.fromkeys(values))
        if len(values) >= 2:
            out[node.name] = values[:20]
    return out


def _run_script(source, options=None):
    with tempfile.TemporaryDirectory(prefix='netcoop_import_') as tmp:
        script, out = Path(tmp) / 'telemetry_source.py', Path(tmp) / 'result.json'
        script.write_text(source, encoding='utf-8')
        try:
            proc = subprocess.run(
                [sys.executable, '-I', '-c', HARNESS, str(script), str(out), str(ROOT), json.dumps(options or {})],
                cwd=tmp, env={}, capture_output=True, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise ValueError(f'The script did not finish within {TIMEOUT_SECONDS} seconds.')
        if not out.exists():
            detail = proc.stderr.decode('utf-8', 'replace').strip().splitlines()
            raise ValueError('The script could not be run: ' + (detail[-1][:300] if detail else 'no output produced.'))
        if out.stat().st_size > MAX_BYTES * 4:
            raise ValueError('The script produced too much data.')
        result = json.loads(out.read_text(encoding='utf-8'))
    if not result.get('ok'):
        raise ValueError(result.get('error', 'Unknown import error.'))
    return result['telemetry'], result['how']


def adapt(t):
    """Make common schema-version variations loadable. Returns (telemetry, notes)."""
    notes = []
    key = 'schema_version' if 'schema_version' in t else ('schema' if 'schema' in t else None)
    val = t.get(key) if key else None
    text = str(val).strip().lower() if val is not None else ''
    legacy_shape, new_shape = bool({'nodes', 'kpi'} & t.keys()), bool({'devices', 'metrics'} & t.keys())
    ver = None
    if text:
        m = re.search(r'(\d+(?:\.\d+)?)\s*$', text)  # "1.0", "v1", "netcoop.telemetry/1.0"
        ver = {'1': '1.0', '1.0': '1.0', '0.9': '0.9'}.get(m.group(1)) if m else None
        if ver and text != ver:
            notes.append(f'Schema {val!r} treated as {ver}.')
    elif legacy_shape != new_shape:
        ver = '0.9' if legacy_shape else '1.0'
        notes.append(f'No schema version in the file; assumed {ver} from its field names.')
    if ver is None:
        found = ', '.join(list(t.keys())[:12]) or 'none'
        shown = repr(val) if key else 'missing'
        raise ValueError(f'Unsupported schema ({shown}). Expected "1.0" (devices, metrics) or "0.9" (nodes, kpi). Top-level keys found: {found}.')
    t = dict(t)
    t.pop('schema_version', None)
    t.pop('schema', None)
    t['schema' if ver == '0.9' else 'schema_version'] = ver
    return t, notes


def convert_any(item, name=None):
    """Convert one snapshot (flat single-device record or schema 1.0/0.9) to schema 1.0. Returns (telemetry, notes)."""
    return convert_flat(item, name) if is_flat_record(item) else adapt(item)


def _load(filename, content, allow_python):
    if len(content.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Please choose a file smaller than 250 KB.')
    name = (filename or '').lower()
    if name.endswith('.py'):
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            raise ValueError(f'Python syntax error on line {exc.lineno}: {exc.msg}')
        found = _literal_telemetry(tree)
        if found is not None:
            return found, 'data literal in the file (nothing was executed)'
        if not allow_python:
            raise ValueError('Running Python imports is only enabled when the dashboard is opened on the same computer as the server.')
        return _run_script(content, _scenario_options(tree))
    try:
        return json.loads(content), 'JSON file'
    except ValueError as exc:
        raise ValueError(f'Not valid JSON: {exc}')


def extract_many(filename, content, allow_python=True):
    """Return ([(name, telemetry, notes), ...], how). Handles one snapshot or several named ones."""
    data, how = _load(filename, content, allow_python)
    if not isinstance(data, dict):
        raise ValueError('Telemetry must be a JSON object.')
    items = list(data.items()) if is_container(data) else [(None, data)]
    out = []
    for name, item in items:
        try:
            telemetry, notes = convert_any(item, name)
        except ValueError as exc:
            raise ValueError(f'{name}: {exc}' if name else str(exc))
        out.append((name, telemetry, notes))
    if len(out) > 1:
        how += f' with {len(out)} named snapshots'
    return out, how


def extract(filename, content, allow_python=True):
    """Single-snapshot helper: (telemetry, how). Uses the first snapshot if the file holds several."""
    items, how = extract_many(filename, content, allow_python)
    name, telemetry, notes = items[0]
    return telemetry, how + (' | ' + ' '.join(notes) if notes else '')
