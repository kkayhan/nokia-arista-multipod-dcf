#!/usr/bin/env python3
"""
Patch the eli telemetry dashboard into the nokia-arista-multipod-dcf dashboard:
  - flow panel (id=1): embed our multi-vendor SVG + panelConfig, 6 targets
    (A-C = SR Linux native; D-F = Arista OpenConfig rate()*8)
  - DC Fabric Throughput (id=22) + per-$NE Throughput (id=25): add Arista targets
  - BGP Peer Stats (id=10): add Arista EVPN session count
  - uid / title / refresh

Reads : telemetry/eli-base.json (pristine eli copy), telemetry/topology.svg,
        telemetry/panelConfig.yaml
Writes: configs/grafana/dashboards/nokia-arista-multipod-dcf-telemetry.json
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(HERE, "eli-base.json")
OUT = os.path.join(ROOT, "configs/grafana/dashboards/nokia-arista-multipod-dcf-telemetry.json")
SVG = open(os.path.join(HERE, "topology.svg")).read()
PANELCONFIG = open(os.path.join(HERE, "panelConfig.yaml")).read()

PROM = "PBFA97CFB590B2093"
DEFNODE = "nokia-leaf1"

# Arista OpenConfig metric names (verify live; patch here if they differ)
A_OUT = "interfaces_interface_state_counters_out_octets"
A_IN = "interfaces_interface_state_counters_in_octets"
A_OPER = "interfaces_interface_state_oper_status"
A_BGP = "network_instances_network_instance_protocols_protocol_bgp_neighbors_neighbor_state_session_state"

d = json.load(open(BASE))
by_id = {p["id"]: p for p in d["panels"]}


def ds():
    return {"type": "prometheus", "uid": PROM}


def ftgt(refid, expr, legend):
    """flow-panel target: instant, no range."""
    return {"datasource": ds(), "expr": expr, "legendFormat": legend, "refId": refid,
            "instant": True, "range": False, "exemplar": False, "interval": "1s",
            "editorMode": "code"}


def tgt(refid, expr, legend):
    return {"datasource": ds(), "expr": expr, "legendFormat": legend, "refId": refid,
            "instant": False, "range": True, "editorMode": "code"}


# ---- flow panel (id=1) ----
flow = by_id[1]
flow["title"] = "Multi-vendor Fabric — live topology & per-link traffic"
o = flow["options"]
o["svg"] = SVG
o["panelConfig"] = PANELCONFIG
o["panZoomEnabled"] = True
o["debuggingCtr"] = {"colorsCtr": 0, "dataCtr": 0, "displaySvgCtr": 0, "mappingsCtr": 0, "timingsCtr": 0}
flow["datasource"] = ds()
flow["targets"] = [
    # SR Linux (native traffic-rate gauges)
    ftgt("A", "interface_oper_state", "oper-state:{{source}}:{{interface_name}}"),
    ftgt("B", "last_over_time(interface_traffic_rate_out_bps[20s])", "{{source}}:{{interface_name}}:out"),
    ftgt("C", "last_over_time(interface_traffic_rate_in_bps[20s])", "{{source}}:{{interface_name}}:in"),
    # Arista cEOS (OpenConfig: octet counters -> rate*8; oper-status enum -> int)
    ftgt("D", A_OPER, "oper-state:{{source}}:{{interface_name}}"),
    ftgt("E", f"rate({A_OUT}[1m])*8", "{{source}}:{{interface_name}}:out"),
    ftgt("F", f"rate({A_IN}[1m])*8", "{{source}}:{{interface_name}}:in"),
]

# ---- DC Fabric Throughput (id=22): add Arista (filter Ethernet to cut noise) ----
p22 = by_id[22]
p22["targets"] += [
    tgt("C", f'rate({A_IN}{{interface_name=~"Ethernet.*"}}[1m])*8', "{{source}}:{{interface_name}}:IN"),
    tgt("D", f'rate({A_OUT}{{interface_name=~"Ethernet.*"}}[1m])*8', "{{source}}:{{interface_name}}:OUT"),
]

# ---- Throughput per $NE (id=25): add Arista (single node -> only one vendor matches) ----
p25 = by_id[25]
p25["targets"] += [
    tgt("C", f'rate({A_IN}{{source="$NE"}}[1m])*8', "{{interface_name}}:IN"),
    tgt("D", f'rate({A_OUT}{{source="$NE"}}[1m])*8', "{{interface_name}}:OUT"),
]

# ---- BGP Peer Stats (id=10): add Arista EVPN established-session count ----
p10 = by_id[10]
p10["targets"].append(
    tgt("D", f'sum({A_BGP}{{source="$NE"}})', "EVPN Sessions Up (Arista)"))
p10["targets"][-1]["instant"] = False

# ---- dashboard meta ----
d["uid"] = "nokia-arista-multipod-dcf"
d["title"] = "Nokia + Arista Multi-Pod DCF — Telemetry"
d["refresh"] = "5s"
d["time"] = {"from": "now-15m", "to": "now"}

for v in d.get("templating", {}).get("list", []):
    if v.get("name") == "NE":
        v["current"] = {"text": DEFNODE, "value": DEFNODE, "selected": True}

json.dump(d, open(OUT, "w"), indent=2)
print(f"wrote {OUT}")
print(f"  size={os.path.getsize(OUT)}B  panels={len(d['panels'])}  flow-targets={len(flow['targets'])}")
