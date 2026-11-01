"""Adapted telemetry fixtures and baseline specialist rules from the supplied prototype."""
import time, uuid, random

SCENARIOS = ["normal", "congestion", "weak_wifi", "interface_fault", "dns_failure", "interop_legacy", "malformed"]

# ---------- synthetic telemetry (schema netcoop.telemetry/1.0) ----------
def generate(s, seed=7):
    r = random.Random(seed); j = lambda a, b: round(r.uniform(a, b), 1)
    dev = lambda i, t: dict(id=i, type=t, status="up", cpu_pct=j(15, 35), mem_pct=j(35, 55), if_errors=r.randint(0, 3),
                            queue_drops=j(0, 6), link_util_pct=j(30, 55))
    devs = [dev("CORE_RTR_01", "router"), dev("HOSTEL_CORE_SW_01", "switch"), dev("DEPT_SW_02", "switch"), dev("HOSTEL_AP_07", "ap")]
    devs[3].update(signal_dbm=j(-58, -48), retransmit_pct=j(1, 3))
    t = dict(schema_version="1.0", timestamp=time.time(), devices=devs,
             links=[["CORE_RTR_01", "HOSTEL_CORE_SW_01"], ["CORE_RTR_01", "DEPT_SW_02"], ["HOSTEL_CORE_SW_01", "HOSTEL_AP_07"]],
             metrics=dict(latency_ms=j(12, 25), jitter_ms=j(1, 4), packet_loss_pct=j(0, .3), throughput_mbps=j(400, 600), bandwidth_mbps=1000),
             services=dict(dns="ok", dhcp="ok"))
    d = {x["id"]: x for x in devs}
    if s == "congestion" or s == "interop_legacy":
        d["HOSTEL_CORE_SW_01"].update(link_util_pct=94, queue_drops=160, cpu_pct=62)
        t["metrics"].update(latency_ms=280, jitter_ms=18, packet_loss_pct=3.1, throughput_mbps=930)
    if s == "weak_wifi":
        d["HOSTEL_AP_07"].update(signal_dbm=-84, retransmit_pct=27)
        t["metrics"].update(latency_ms=95, jitter_ms=41, packet_loss_pct=4.2, throughput_mbps=60)
    if s == "interface_fault":
        d["DEPT_SW_02"].update(if_errors=830, status="degraded")
        t["metrics"].update(latency_ms=70, jitter_ms=25, packet_loss_pct=6.5)
    if s == "dns_failure":
        t["services"]["dns"] = "fail"; t["metrics"].update(latency_ms=22)
    if s == "interop_legacy":  # old schema: other names, fractions, seconds; memory field missing
        return dict(schema="0.9", ts=t["timestamp"], nodes=[dict(name=x["id"], kind=x["type"], state=x["status"], cpu=x["cpu_pct"] / 100,
                    util=x["link_util_pct"] / 100, drops=x["queue_drops"], errors=x["if_errors"]) for x in devs],
                    edges=t["links"], kpi=dict(latency_s=t["metrics"]["latency_ms"] / 1000, jitter_s=t["metrics"]["jitter_ms"] / 1000,
                    loss_ratio=t["metrics"]["packet_loss_pct"] / 100, throughput_mbps=t["metrics"]["throughput_mbps"], bandwidth_mbps=1000))
    if s == "malformed":
        return dict(schema_version="1.0", devices="not-a-list", metrics=None)
    return t

# ---------- interoperability: normalise any known schema to 1.0 ----------
def normalize(raw):
    if not isinstance(raw, dict): raise ValueError("telemetry must be a JSON object")
    w, legacy = [], raw.get("schema") == "0.9"
    devs_raw = raw.get("nodes" if legacy else "devices"); m = raw.get("kpi" if legacy else "metrics")
    if not isinstance(devs_raw, list) or not devs_raw or not isinstance(m, dict):
        raise ValueError("missing or invalid 'devices'/'metrics' (expected list and object)")
    if legacy: w.append("legacy schema 0.9 detected: converted fractions->%, seconds->ms, renamed fields")
    devs = []
    for x in devs_raw:
        g = lambda *k: next((x[a] for a in k if a in x), None)
        f = 100 if legacy else 1
        c, u = g("cpu_pct", "cpu"), g("link_util_pct", "util")
        dv = dict(id=g("id", "name"), type=g("type", "kind"), status=g("status", "state") or "unknown",
                  cpu_pct=c * f if c is not None else None, mem_pct=g("mem_pct", "mem"), if_errors=g("if_errors", "errors"),
                  queue_drops=g("queue_drops", "drops"), link_util_pct=u * f if u is not None else None,
                  signal_dbm=g("signal_dbm", "rssi"), retransmit_pct=g("retransmit_pct"))
        if not dv["id"]: w.append("device without id skipped"); continue
        miss = [k for k in ("cpu_pct", "mem_pct", "if_errors", "queue_drops", "link_util_pct") if dv[k] is None and dv["type"] != "ap"]
        if miss: w.append(f"{dv['id']}: missing {','.join(miss)}")
        devs.append(dv)
    mm = dict(latency_ms=m.get("latency_ms", m["latency_s"] * 1000 if "latency_s" in m else None),
              jitter_ms=m.get("jitter_ms", m["jitter_s"] * 1000 if "jitter_s" in m else None),
              packet_loss_pct=m.get("packet_loss_pct", m["loss_ratio"] * 100 if "loss_ratio" in m else None),
              throughput_mbps=m.get("throughput_mbps"), bandwidth_mbps=m.get("bandwidth_mbps"))
    return dict(devices=devs, links=raw.get("links", raw.get("edges", [])), metrics=mm, services=raw.get("services", {})), w

# ---------- message envelope (netcoop.finding/1.0) ----------
def msg(sender, recipient, mtype, payload):
    return dict(msg_id=uuid.uuid4().hex[:8], schema="netcoop.message/1.0", sender=sender, recipient=recipient, type=mtype,
                ts=round(time.time(), 3), payload=payload)

def F(signal, value, unit, sev, text, device=None):
    return dict(signal=signal, value=value, unit=unit, severity=sev, interpretation=text, device=device)

# ---------- specialised agents: return (findings, support{cause: weight}) ----------
def performance_agent(n):
    m, f, s = n["metrics"], [], {}
    def add(c, w): s[c] = round(s.get(c, 0) + w, 2)
    L, J, P = m["latency_ms"], m["jitter_ms"], m["packet_loss_pct"]
    if L is not None and L > 100: f.append(F("latency_ms", L, "ms", .8, "Elevated latency")); add("link_congestion", .35); add("interface_fault", .1)
    if J is not None and J > 20: f.append(F("jitter_ms", J, "ms", .6, "High jitter")); add("weak_wifi", .25); add("interface_fault", .2); add("link_congestion", .1)
    if P is not None and P > 2: f.append(F("packet_loss_pct", P, "%", .8, "Significant packet loss")); add("interface_fault", .25); add("weak_wifi", .2); add("link_congestion", .2)
    if m["throughput_mbps"] and m["bandwidth_mbps"] and m["throughput_mbps"] / m["bandwidth_mbps"] > .85:
        f.append(F("throughput_ratio", round(m["throughput_mbps"] / m["bandwidth_mbps"], 2), "ratio", .8, "Throughput near capacity")); add("link_congestion", .3)
    if m["throughput_mbps"] is not None and m["throughput_mbps"] < 100: f.append(F("throughput_mbps", m["throughput_mbps"], "Mbps", .6, "Very low throughput")); add("weak_wifi", .15)
    return f, s

def infrastructure_agent(n):
    f, s = [], {}
    def add(c, w): s[c] = round(s.get(c, 0) + w, 2)
    for d in n["devices"]:
        i = d["id"]
        if (d["link_util_pct"] or 0) > 85: f.append(F("link_utilization_pct", d["link_util_pct"], "%", .9, "High link utilization", i)); add("link_congestion", .45)
        if (d["queue_drops"] or 0) > 50: f.append(F("queue_drops", d["queue_drops"], "pkts/s", .9, "Elevated egress queue drops", i)); add("link_congestion", .4)
        if (d["if_errors"] or 0) > 100: f.append(F("interface_errors", d["if_errors"], "count", .9, "Rising interface errors", i)); add("interface_fault", .7)
        if (d["cpu_pct"] or 0) > 85: f.append(F("cpu_pct", d["cpu_pct"], "%", .8, "Device CPU overload", i)); add("device_overload", .6)
        if d["status"] not in ("up", "unknown"): f.append(F("device_status", d["status"], "enum", .7, "Device not healthy", i)); add("interface_fault", .2)
    return f, s

def connectivity_agent(n):
    f, s = [], {}
    for d in n["devices"]:
        if d.get("signal_dbm") is not None and d["signal_dbm"] < -75: f.append(F("signal_dbm", d["signal_dbm"], "dBm", .9, "Weak wireless signal", d["id"])); s["weak_wifi"] = s.get("weak_wifi", 0) + .5
        if (d.get("retransmit_pct") or 0) > 15: f.append(F("retransmit_pct", d["retransmit_pct"], "%", .8, "High Wi-Fi retransmissions", d["id"])); s["weak_wifi"] = s.get("weak_wifi", 0) + .4
    for k, v in n["services"].items():
        if v != "ok": f.append(F(f"{k}_status", v, "enum", .95, f"{k.upper()} service failing")); s["dns_dhcp_failure"] = s.get("dns_dhcp_failure", 0) + .9
    return f, s

ACTIONS = {
 "link_congestion": ["Inspect uplink/egress utilization on the affected switch", "Review QoS/queue configuration and traffic distribution", "Consider link aggregation or bandwidth upgrade"],
 "weak_wifi": ["Check AP placement/channel plan and client distance", "Raise AP power or add an AP in the affected zone", "Look for co-channel interference"],
 "interface_fault": ["Inspect cable/SFP/port on the affected device", "Check duplex/speed negotiation", "Replace suspected cable or move port"],
 "dns_dhcp_failure": ["Verify DNS/DHCP server reachability and service status", "Check DHCP pool exhaustion and resolver config", "Fail over to secondary server"],
 "device_overload": ["Inspect control-plane load and top processes", "Reduce polling/ACL load or upgrade device"],
 "normal": ["No action required; continue monitoring"]}
