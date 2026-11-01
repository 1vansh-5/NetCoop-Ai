"""Pluggable telemetry provider.

A provider is an ordinary Python file (default: telemetry_provider.py next to this
module, or the path in NETCOOP_PROVIDER). Every time an investigation asks the MCP
`get_telemetry` tool for a `provider:<scenario>` scenario, the file is run again in
its own process and whatever it returns becomes the telemetry the agents analyse.

The provider only needs a function that returns one telemetry dict, for example

    def generate_telemetry(fault_type="normal"): ...

Scenario names are discovered from the function's `if fault_type == "..."` branches,
or from an optional top-level SCENARIOS = ["a", "b"] list. The returned dict may be
NetCoop schema 1.0/0.9 or a single-device record (device_id, status, metrics).
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from importer import convert_any, _scenario_options

ROOT = Path(__file__).resolve().parent
PREFIX = 'provider:'
MAX_BYTES = 250_000
_cache = {}

HARNESS = r'''
import contextlib, inspect, io, json, os, runpy, sys
path, out, scenario, func = sys.argv[1:5]
sys.path.insert(0, os.path.dirname(path))

def write(obj):
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(obj, f, default=str)

try:
    with contextlib.redirect_stdout(io.StringIO()):  # provider prints must never reach the MCP protocol stream
        ns = runpy.run_path(path, run_name='telemetry_provider')
        candidates = ([func] if func else []) + ['get_telemetry', 'generate_telemetry', 'generate', 'telemetry', 'collect', 'main']
        fn = next((ns[n] for n in candidates if n in ns and callable(ns[n])), None)
        if fn is None:
            fn = next((v for k, v in ns.items() if inspect.isfunction(v) and not k.startswith('_') and v.__module__ == 'telemetry_provider'), None)
        if fn is None:
            raise LookupError('no telemetry function found (define e.g. generate_telemetry)')
        takes_arg = bool(inspect.signature(fn).parameters)
        value = fn(scenario) if (takes_arg and scenario != 'default') else fn()
    write({'ok': True, 'telemetry': value, 'function': fn.__name__})
except BaseException as exc:
    write({'ok': False, 'error': f'{type(exc).__name__}: {str(exc)[:300]}'})
'''


def provider_path():
    p = Path(os.getenv('NETCOOP_PROVIDER', 'telemetry_provider.py'))
    return p if p.is_absolute() else ROOT / p


def inspect_provider():
    """Describe the provider: availability, function and scenario names. Cached until the file changes."""
    p = provider_path()
    info = {'available': False, 'file': p.name, 'function': None, 'scenarios': [], 'error': None}
    if not p.is_file():
        info['error'] = f'{p.name} was not found next to server.py (set NETCOOP_PROVIDER to use another path).'
        return info
    key = (str(p), p.stat().st_mtime_ns)
    if key in _cache:
        return _cache[key]
    try:
        tree = ast.parse(p.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        info['error'] = f'{p.name} could not be read: {exc}'
        return info
    names = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SCENARIOS' for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                continue
            if isinstance(value, (list, tuple)) and value and all(isinstance(x, str) for x in value):
                names = list(value)
    options = _scenario_options(tree)
    if options:
        info['function'], values = next(iter(options.items()))
        names = names or values
    info.update(available=True, scenarios=names or ['default'])
    _cache.clear()
    _cache[key] = info
    return info


def has_scenario(scenario):
    info = inspect_provider()
    return scenario.startswith(PREFIX) and info['available'] and scenario[len(PREFIX):] in info['scenarios']


def fetch(scenario):
    """Run the provider for one scenario and return schema 1.0 telemetry. Raises ValueError with a readable message."""
    name = scenario[len(PREFIX):] if scenario.startswith(PREFIX) else scenario
    info = inspect_provider()
    if not info['available']:
        raise ValueError('Telemetry provider unavailable: ' + info['error'])
    if name not in info['scenarios']:
        raise ValueError(f"Unknown provider scenario {name!r}. {info['file']} offers: {', '.join(info['scenarios'])}.")
    p, started = provider_path(), time.monotonic()
    timeout = float(os.getenv('NETCOOP_PROVIDER_TIMEOUT', '10'))
    with tempfile.TemporaryDirectory(prefix='netcoop_provider_') as tmp:
        out = Path(tmp) / 'result.json'
        env = {k: v for k, v in os.environ.items() if k != 'GEMINI_API_KEY'}
        try:
            proc = subprocess.run([sys.executable, '-c', HARNESS, str(p), str(out), name, info['function'] or ''],
                                  cwd=p.parent, env=env, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ValueError(f'Telemetry provider {p.name} did not finish within {timeout:g} seconds.')
        if not out.exists():
            detail = proc.stderr.decode('utf-8', 'replace').strip().splitlines()
            raise ValueError(f'Telemetry provider {p.name} could not be run: ' + (detail[-1][:300] if detail else 'no output.'))
        if out.stat().st_size > MAX_BYTES * 4:
            raise ValueError('Telemetry provider returned too much data.')
        result = json.loads(out.read_text(encoding='utf-8'))
    if not result.get('ok'):
        raise ValueError(f'Telemetry provider {p.name} failed: {result.get("error")}')
    value = result['telemetry']
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise ValueError(f'Telemetry provider {p.name} returned text that is not JSON.')
    if not isinstance(value, dict):
        raise ValueError(f'Telemetry provider {p.name} must return one telemetry object.')
    telemetry, notes = convert_any(value, name)
    elapsed = round((time.monotonic() - started) * 1000)
    telemetry = dict(telemetry)
    telemetry['provider'] = {'file': p.name, 'function': result['function'], 'scenario': name, 'duration_ms': elapsed}
    telemetry['import_notes'] = [f'Telemetry produced live by {p.name} ({result["function"]}) for scenario {name!r}.'] + notes
    return telemetry
