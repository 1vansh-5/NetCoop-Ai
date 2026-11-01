"""Real stdio MCP server. stdout is reserved for the protocol."""
from mcp.server.mcpserver import MCPServer
from netcoop import generate, normalize, analyze, runbook
from provider import fetch, PREFIX

mcp = MCPServer('NetCoop Diagnostic Tools')

@mcp.tool()
def get_telemetry(scenario: str = 'normal', seed: int = 7) -> dict:
    """Read campus telemetry. `provider:<name>` runs the telemetry provider script; other names are reproducible synthetic scenarios. Never polls production."""
    if scenario.startswith(PREFIX):
        try:
            return fetch(scenario)
        except ValueError as exc:  # return the reason as data; a raised error would reach the client as a generic failure
            return {'provider_error': str(exc)}
    return generate(scenario, seed)

@mcp.tool()
def normalize_telemetry(raw: dict) -> dict:
    """Validate schema, convert legacy units, and measure data completeness/freshness."""
    return normalize(raw)

@mcp.tool()
def analyze_specialist(agent: str, telemetry: dict) -> dict:
    """Run performance, infrastructure, or connectivity specialist on normalized telemetry."""
    return analyze(agent, telemetry)

@mcp.tool()
def inspect_device(device_id: str, telemetry: dict) -> dict:
    """Read one device and adjacent topology from this incident's telemetry."""
    return {'device': next((d for d in telemetry['devices'] if d['id']==device_id),None), 'links':[e for e in telemetry['links'] if device_id in e]}

@mcp.tool()
def get_runbook(cause: str) -> dict:
    """Retrieve human-review corrective actions for a diagnostic hypothesis."""
    return runbook(cause)

@mcp.resource('netcoop://protocol')
def protocol() -> str:
    return 'netcoop.message/1.0: msg_id, run_id, sequence, sender, recipient, type, ts, payload. Findings: signal, value, unit, severity, interpretation, device. Units: ms, %, dBm, Mbps, pkts/s, count. Telemetry: schema_version 1.0 or legacy schema 0.9.'

if __name__ == '__main__':
    mcp.run()
