# NetCoop interoperability protocol

## Envelope: netcoop.message/1.0

```json
{
  "schema": "netcoop.message/1.0",
  "msg_id": "unique-uuid-hex",
  "run_id": "INC-12345678",
  "sequence": 12,
  "ts": 1793460000.123,
  "sender": "infrastructure",
  "recipient": "correlation",
  "type": "finding",
  "payload": {
    "agent": "infrastructure",
    "findings": [{
      "signal": "link_utilization_pct",
      "value": 94,
      "unit": "%",
      "severity": 0.9,
      "interpretation": "High link utilization",
      "device": "HOSTEL_CORE_SW_01"
    }],
    "support": {"link_congestion": 0.45}
  }
}
```

`msg_id` identifies a message, `run_id` correlates the incident, `sequence` orders all events in that incident, and `ts` is Unix seconds. `sender` and `recipient` identify logical roles; physical tool calls use the separate MCP JSON-RPC transport. `type` is one of plan, connected, tool_call, tool_result, telemetry_source, normalized, finding, hypothesis, reasoning, narrative, final_report or error. `telemetry_source` is sent when a provider script supplied the telemetry and names the file, function, scenario and run time. Payload schema follows event type. These message events are diagnostic/application messages, not a replacement for MCP's JSON-RPC envelopes.

`severity` is a rule-specific 0–1 salience value for a finding; scoring uses the explicit `support` weights rather than multiplying severity again. `device: null` means network-wide or not localizable. `support` maps hypotheses to non-negative evidence weights. Normalized data is passed independently to each specialist; agents return structured messages rather than parsing free-text from each other.

## Telemetry schema 1.0

Required: `schema_version: "1.0"`, a non-empty `devices` array, and a `metrics` object. Missing measurements are allowed and reduce data coverage; missing timestamps force an insufficient-evidence result.

| Field | Meaning / unit |
|---|---|
| timestamp | Unix seconds of observation |
| devices[].id | Unique string, 1–100 characters |
| devices[].type | Device category, typically router/switch/ap |
| devices[].status | up/down/degraded/unknown |
| cpu_pct, mem_pct, link_util_pct, retransmit_pct | Percentage, 0–100 |
| if_errors | Non-negative interface error count in the supplied sample |
| queue_drops | Non-negative packets/second |
| signal_dbm | RSSI, -150 to 0 dBm |
| metrics.latency_ms, jitter_ms | Non-negative milliseconds |
| metrics.packet_loss_pct | Percentage, 0–100 |
| metrics.throughput_mbps, bandwidth_mbps | Non-negative Mbps |
| links | Array of two existing device IDs per edge |
| services | dns/dhcp entries with ok/fail/unknown |

Numeric strings, booleans, NaN and Infinity are rejected. Inputs are limited to 200 devices, 250 KB at the diagnosis API, and supported schema versions. Unknown numeric metrics are not used by diagnostic rules. Unknown root-level fields are ignored. No automatic claim is made about cumulative counter rates; interface error count is a snapshot indicator and must be independently verified over time.

## Legacy schema 0.9

`schema: "0.9"`, `ts`, `nodes`, `edges`, `kpi` map to schema 1.0. Device `name/kind/state` map to `id/type/status`; `cpu` and `util` fractions multiply by 100. `drops/errors` map to queue drops/interface errors. KPI `latency_s/jitter_s` multiply by 1000, and `loss_ratio` multiplies by 100. Unavailable memory remains null. Every conversion appears in quality warnings.

## Report and failure semantics

Every report has `incident_id`, `status`, `cause`, `suspected_root_cause`, `confidence`, `affected_devices`, `supporting_evidence`, `alternative_causes`, `recommended_actions`, `evidence_sources` and `limitations`.

- `diagnosed`: available evidence supports a probable fault or a sufficiently observed normal baseline.
- `insufficient_evidence`: partial/stale data, insufficient weight, competing scores, or too few successful specialists.
- `error`: schema/transport failure prevented a report. Confidence is zero and limitations explain the failure.

The report includes `scores`, `data_quality`, `potentially_impacted_neighbors`, `ai`, timestamps and duration when available. `ai.status` is offline, connected, unavailable or limited. Only connected means a non-empty Google-generated response was returned. No provider connection is inferred from a configured key alone.

## Persistence and ordering

Each run uses a dedicated MCP subprocess/session to isolate inputs. Events are appended in observed order, so parallel specialist completion order can vary while sequence numbers remain unique and increasing. SQLite writes occur after the final report; the stream's `complete` event follows persistence. A browser disconnect cancels the active run. History contains completed reports, including handled error reports, but does not resume partial runs.
