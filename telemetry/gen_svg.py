#!/usr/bin/env python3
"""
Generate the nokia-arista-multipod-dcf topology SVG (self-contained, light theme)
+ the andrewbmchugh-flow-panel panelConfig.

eli style: every physical link is split at its midpoint into TWO directional
half-segments, each = a coloured line + arrow (pointing toward the midpoint =
the egress direction of its source) + a live throughput-rate label. Both
directions' rate shown.

Nodes use draw.io device ICONS (icon_switch.svg = spine/leaf, icon_host.svg = host).
Vendor colour: Nokia = blue, Arista = teal, hosts = slate.

DataRef naming (MUST match the flow-panel target legendFormats in the dashboard):
  Nokia SRL (gnmic rename-srl-interface):   <node>:e1-X      (oper-state / out / in)
  Arista cEOS (OpenConfig, no rename):      <node>:EthernetN (oper-state / out / in)
  Hosts (no gNMI metric): bind to the LEAF side — fwd=leaf:if:out, rev=leaf:if:in,
                          oper reuse leaf:if.

Topology (from nokia-arista-multipod-dcf.clab.yaml):
  Pod-Nokia : nokia-spine1/2 (e1-1..4 downlinks, e1-21/22 inter-pod),
              nokia-leaf1..4 (e1-33->spine1, e1-34->spine2, e1-1->host)
  Pod-Arista: arista-spine1/2 (eth3..6 downlinks, eth1/2 inter-pod),
              arista-leaf5..8 (eth2->spine1, eth3->spine2, eth4/5 MLAG peer, eth1->host)
  Inter-pod : nokia-spineN:e1-21/22 <-> arista-spineM:eth1/2  (full mesh, 4 links)
  Hosts     : h1->nleaf1/2, h2->nleaf3/4, h3->aleaf5/6, h4->aleaf7/8
"""
import os, re, math

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_SWITCH = open(os.path.join(HERE, "icon_switch.svg")).read()
ICON_HOST = open(os.path.join(HERE, "icon_host.svg")).read()

# ---- canvas / layout ------------------------------------------------------
W, H = 1740, 880
Y_SPINE, S_SPINE = 185, 74
Y_LEAF,  S_LEAF  = 480, 62
Y_HOST,  S_HOST  = 715, 44

NSPINE = {1: 330, 2: 510}
NLEAF  = {1: 150, 2: 330, 3: 510, 4: 690}
NHOST  = {"h1": 240, "h2": 600}
ASPINE = {1: 1230, 2: 1410}
ALEAF  = {5: 1050, 6: 1230, 7: 1410, 8: 1590}
AHOST  = {"h3": 1140, "h4": 1500}

NOKIA_SPINE_FILL, NOKIA_LEAF_FILL = "#1D4ED8", "#3B82F6"   # blue
ARISTA_SPINE_FILL, ARISTA_LEAF_FILL = "#0F766E", "#14B8A6"  # teal
HOST_FILL = "#64748B"                                       # slate

# ---- icon placement (from neocloud gen_svg.py) ----------------------------
def place_icon(template, uid, fill, cx, cy, size):
    icon = template
    old = re.search(r'id="(svg-image-[^"]+)"', icon).group(1)
    icon = icon.replace(old, uid)
    icon = re.sub(r'(\.st0 \{ fill: )[^;]+;', r'\g<1>%s;' % fill, icon, count=1)
    op = icon.find('>', icon.find('<svg version="1.1"'))
    head, rest = icon[:op + 1], icon[op + 1:]
    x, y = cx - size / 2, cy - size / 2
    head = re.sub(r' x="[^"]*"', f' x="{x:.1f}"', head, count=1)
    head = re.sub(r' y="[^"]*"', f' y="{y:.1f}"', head, count=1)
    head = re.sub(r' width="[^"]*"',  f' width="{size:.1f}"',  head, count=1)
    head = re.sub(r' height="[^"]*"', f' height="{size:.1f}"', head, count=1)
    return head + rest

def text(x, y, s, size=15, fill="#0f172a", weight="600", anchor="middle"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{s}</text>')

# ---- dual-half link primitives --------------------------------------------
MID_ELLIPSE = ('<g id="cell-mid:{A}:{AIF}:{B}:{BIF}" data-label=""><ellipse cx="{MX:.1f}" cy="{MY:.1f}" '
               'rx="2.5" ry="2.5" fill="#94a3b8" stroke="none"/></g>')

HALF_LINK = ('<g id="cell-link_id:{A}:{AIF}:{B}:{BIF}" data-label="rate" data-source="{A}:{AIF}:{B}:{BIF}" '
             'data-target="mid:{MA}:{MAIF}:{MB}:{MBIF}">'
             '<path d="M {X1:.1f} {Y1:.1f} L {X2:.1f} {Y2:.1f}" fill="none" stroke="#cbd5e1" stroke-width="4" '
             'stroke-linecap="round" pointer-events="stroke"/>'
             '<path d="{ARROW}" fill="#cbd5e1" stroke="#cbd5e1" stroke-width="1"/>'
             '<g transform="translate(-0.5 -0.5)"><switch><foreignObject style="overflow: visible; text-align: left;" '
             'pointer-events="none" width="100%" height="100%" requiredFeatures="http://www.w3.org/TR/SVG11/feature#Extensibility">'
             '<div xmlns="http://www.w3.org/1999/xhtml" style="display: flex; align-items: unsafe center; justify-content: unsafe center; '
             'width: 1px; height: 1px; padding-top: {LY:.0f}px; margin-left: {LX:.0f}px;">'
             '<div style="box-sizing: border-box; font-size: 0; text-align: center;">'
             '<div style="display: inline-block; font-size: 10px; font-weight: 600; color: #0f172a; line-height: 1.2; '
             'pointer-events: all; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px; '
             'padding: 0px 3px; white-space: nowrap;">rate</div></div></div></foreignObject></switch></g></g>')

PORT_FILL = ('<g id="cell-{A}:{AIF}:{B}:{BIF}"><ellipse cx="{X:.1f}" cy="{Y:.1f}" rx="6" ry="6" '
             'fill="#94a3b8" stroke="#475569" stroke-width="1"/></g>')

def arrow_head(x1, y1, x2, y2, size=7):
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L == 0:
        return "", x2, y2
    ux, uy = dx / L, dy / L
    bx, by = x2 - ux * size, y2 - uy * size
    wx, wy = -uy, ux
    half = size * 0.55
    w1 = (bx + wx * half, by + wy * half)
    w2 = (bx - wx * half, by - wy * half)
    return (f"M {w1[0]:.1f} {w1[1]:.1f} L {x2:.1f} {y2:.1f} L {w2[0]:.1f} {w2[1]:.1f} Z", bx, by)

links_svg, ports_svg, cells = [], [], []

def make_link(a, aif, b, bif, x1, y1, x2, y2, fwd_dref, rev_dref, a_oper, b_oper, label_dy=0):
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    links_svg.append(MID_ELLIPSE.format(A=a, AIF=aif, B=b, BIF=bif, MX=mx, MY=my))
    ar, ex, ey = arrow_head(x1, y1, mx, my)
    links_svg.append(HALF_LINK.format(A=a, AIF=aif, B=b, BIF=bif, MA=a, MAIF=aif, MB=b, MBIF=bif,
                                      X1=x1, Y1=y1, X2=ex, Y2=ey, ARROW=ar,
                                      LX=(x1 + mx) / 2, LY=(y1 + my) / 2 + label_dy))
    ar, ex, ey = arrow_head(x2, y2, mx, my)
    links_svg.append(HALF_LINK.format(A=b, AIF=bif, B=a, BIF=aif, MA=a, MAIF=aif, MB=b, MBIF=bif,
                                      X1=x2, Y1=y2, X2=ex, Y2=ey, ARROW=ar,
                                      LX=(x2 + mx) / 2, LY=(y2 + my) / 2 + label_dy))
    ports_svg.append(PORT_FILL.format(A=a, AIF=aif, B=b, BIF=bif, X=x1, Y=y1))
    ports_svg.append(PORT_FILL.format(A=b, AIF=bif, B=a, BIF=aif, X=x2, Y=y2))
    cells.append((f"link_id:{a}:{aif}:{b}:{bif}", fwd_dref, "traffic"))
    cells.append((f"link_id:{b}:{bif}:{a}:{aif}", rev_dref, "traffic"))
    cells.append((f"{a}:{aif}:{b}:{bif}", a_oper, "oper"))
    cells.append((f"{b}:{bif}:{a}:{aif}", b_oper, "oper"))

def sw_dref(node, iface, dir_):  # switch endpoint (out/in or oper-state)
    if dir_ == "oper":
        return f"oper-state:{node}:{iface}"
    return f"{node}:{iface}:{dir_}"

# ---- build links ----------------------------------------------------------
# Nokia spine<->leaf : spineS:e1-L  <->  leafL:e1-{33=spine1,34=spine2}
for L in range(1, 5):
    lcx = NLEAF[L]
    for S, lport in ((1, 33), (2, 34)):
        scx = NSPINE[S]
        sx, sy = scx + (L - 2.5) * 14, Y_SPINE + S_SPINE / 2
        lx, ly = lcx + (-12 if S == 1 else 12), Y_LEAF - S_LEAF / 2
        sn, ln = f"nokia-spine{S}", f"nokia-leaf{L}"
        make_link(sn, f"e1-{L}", ln, f"e1-{lport}", sx, sy, lx, ly,
                  sw_dref(sn, f"e1-{L}", "out"), sw_dref(ln, f"e1-{lport}", "out"),
                  sw_dref(sn, f"e1-{L}", "oper"), sw_dref(ln, f"e1-{lport}", "oper"))

# Arista spine<->leaf : spineS:Ethernet{3+idx} <-> leafL:Ethernet{2=spine1,3=spine2}
for idx, L in enumerate(range(5, 9)):
    lcx = ALEAF[L]
    for S, lport in ((1, 2), (2, 3)):
        scx = ASPINE[S]
        sport = 3 + idx                      # leaf5->eth3 ... leaf8->eth6 (same on both spines)
        sx, sy = scx + (idx - 1.5) * 14, Y_SPINE + S_SPINE / 2
        lx, ly = lcx + (-12 if S == 1 else 12), Y_LEAF - S_LEAF / 2
        sn, ln = f"arista-spine{S}", f"arista-leaf{L}"
        make_link(sn, f"Ethernet{sport}", ln, f"Ethernet{lport}", sx, sy, lx, ly,
                  sw_dref(sn, f"Ethernet{sport}", "out"), sw_dref(ln, f"Ethernet{lport}", "out"),
                  sw_dref(sn, f"Ethernet{sport}", "oper"), sw_dref(ln, f"Ethernet{lport}", "oper"))

# Inter-pod spine mesh: nokia-spineN:e1-{21,22} <-> arista-spineM:eth{1,2}
#   nspine1:e1-21->aspine1:eth1 ; nspine1:e1-22->aspine2:eth1
#   nspine2:e1-21->aspine1:eth2 ; nspine2:e1-22->aspine2:eth2
INTERPOD = [
    (1, "e1-21", 1, "Ethernet1"), (1, "e1-22", 2, "Ethernet1"),
    (2, "e1-21", 1, "Ethernet2"), (2, "e1-22", 2, "Ethernet2"),
]
for nS, nif, aS, aif in INTERPOD:
    nx, ny = NSPINE[nS] + S_SPINE / 2, Y_SPINE + (-10 if nif.endswith("21") else 10)
    ax, ay = ASPINE[aS] - S_SPINE / 2, Y_SPINE + (-10 if aif.endswith("1") else 10)
    sn, an = f"nokia-spine{nS}", f"arista-spine{aS}"
    make_link(sn, nif, an, aif, nx, ny, ax, ay,
              sw_dref(sn, nif, "out"), sw_dref(an, aif, "out"),
              sw_dref(sn, nif, "oper"), sw_dref(an, aif, "oper"), label_dy=-6)

# Arista MLAG peer-links: leaf5<->leaf6 (eth4,eth5), leaf7<->leaf8 (eth4,eth5)
for La, Lb in ((5, 6), (7, 8)):
    for k, port in enumerate((4, 5)):
        ax, ay = ALEAF[La] + S_LEAF / 2, Y_LEAF + (k * 2 - 1) * 9
        bx, by = ALEAF[Lb] - S_LEAF / 2, Y_LEAF + (k * 2 - 1) * 9
        na, nb = f"arista-leaf{La}", f"arista-leaf{Lb}"
        make_link(na, f"Ethernet{port}", nb, f"Ethernet{port}", ax, ay, bx, by,
                  sw_dref(na, f"Ethernet{port}", "out"), sw_dref(nb, f"Ethernet{port}", "out"),
                  sw_dref(na, f"Ethernet{port}", "oper"), sw_dref(nb, f"Ethernet{port}", "oper"),
                  label_dy=-10)

# Host links: A=leaf (metric), B=host (no metric -> reuse leaf oper, rev=leaf:in)
HOSTLINKS = [
    ("h1", "eth1", "nokia-leaf1", "e1-1"), ("h1", "eth2", "nokia-leaf2", "e1-1"),
    ("h2", "eth1", "nokia-leaf3", "e1-1"), ("h2", "eth2", "nokia-leaf4", "e1-1"),
    ("h3", "eth1", "arista-leaf5", "Ethernet1"), ("h3", "eth2", "arista-leaf6", "Ethernet1"),
    ("h4", "eth1", "arista-leaf7", "Ethernet1"), ("h4", "eth2", "arista-leaf8", "Ethernet1"),
]
HOST_CX = {**NHOST, **AHOST}
def leaf_cx(node):
    n = int(re.search(r"\d+", node).group())
    return NLEAF.get(n, ALEAF.get(n))
for host, hif, leaf, lif in HOSTLINKS:
    hcx = HOST_CX[host]
    lcx = leaf_cx(leaf)
    toward = 1 if hcx > lcx else -1            # host is to the right(+) or left(-) of leaf
    lx, ly = lcx + toward * 16, Y_LEAF + S_LEAF / 2
    hx, hy = hcx - toward * 12, Y_HOST - S_HOST / 2
    make_link(leaf, lif, host, hif, lx, ly, hx, hy,
              sw_dref(leaf, lif, "out"), sw_dref(leaf, lif, "in"),
              sw_dref(leaf, lif, "oper"), sw_dref(leaf, lif, "oper"))

# ---- assemble SVG ---------------------------------------------------------
svg = []
def add(s): svg.append(s)
add(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
    f'viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Inter,Segoe UI,Helvetica,Arial,sans-serif">')
add(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')

# pod bands (titles left-aligned in the corner so they clear the centered spine labels)
add(f'<rect x="60" y="120" width="720" height="650" rx="18" fill="#EFF6FF" stroke="#1D4ED8" '
    f'stroke-width="1.5" stroke-dasharray="3 4" opacity="0.9"/>')
add(text(86, 146, "POD-NOKIA", size=17, fill="#1D4ED8", weight="800", anchor="start"))
add(text(86, 163, "SR Linux 26.3.2  ·  IS-IS 49.0200", size=10, fill="#3B82F6", weight="600", anchor="start"))
add(f'<rect x="960" y="120" width="720" height="650" rx="18" fill="#F0FDFA" stroke="#0F766E" '
    f'stroke-width="1.5" stroke-dasharray="3 4" opacity="0.9"/>')
add(text(1654, 146, "POD-ARISTA", size=17, fill="#0F766E", weight="800", anchor="end"))
add(text(1654, 163, "cEOS 4.34  ·  IS-IS 49.0078", size=10, fill="#14B8A6", weight="600", anchor="end"))

# title + inter-pod label
add(text(W/2, 40, "nokia-arista-multipod-dcf — stretched EVPN-VXLAN fabric", size=22, fill="#0f172a", weight="800"))
add(text(W/2, 62, "two-vendor single overlay  ·  iBGP-EVPN AS 65524  ·  BD-A 10.110.0.0/24 + BD-B 10.120.0.0/24 (L3 VNI 50001)",
         size=12, fill="#64748b", weight="500"))
add(text(870, Y_SPINE - 52, "inter-pod", size=12, fill="#94a3b8", weight="700"))
add(text(870, Y_SPINE - 38, "IS-IS L2", size=11, fill="#94a3b8", weight="600"))

# links (under icons)
svg += links_svg

# nodes (icons over links)
for S, scx in NSPINE.items():
    add(place_icon(ICON_SWITCH, f"svg-img-nokia-spine{S}", NOKIA_SPINE_FILL, scx, Y_SPINE, S_SPINE))
    add(text(scx, Y_SPINE - S_SPINE/2 - 6, f"nokia-spine{S}", size=13, fill="#0f172a", weight="700"))
for S, scx in ASPINE.items():
    add(place_icon(ICON_SWITCH, f"svg-img-arista-spine{S}", ARISTA_SPINE_FILL, scx, Y_SPINE, S_SPINE))
    add(text(scx, Y_SPINE - S_SPINE/2 - 6, f"arista-spine{S}", size=13, fill="#0f172a", weight="700"))
    add(text(scx, Y_SPINE - S_SPINE/2 - 19, "EVPN RR", size=9, fill="#94a3b8", weight="700"))
for L, lcx in NLEAF.items():
    add(place_icon(ICON_SWITCH, f"svg-img-nokia-leaf{L}", NOKIA_LEAF_FILL, lcx, Y_LEAF, S_LEAF))
    add(text(lcx, Y_LEAF + S_LEAF/2 + 14, f"nokia-leaf{L}", size=12, fill="#0f172a", weight="700"))
for L, lcx in ALEAF.items():
    add(place_icon(ICON_SWITCH, f"svg-img-arista-leaf{L}", ARISTA_LEAF_FILL, lcx, Y_LEAF, S_LEAF))
    add(text(lcx, Y_LEAF + S_LEAF/2 + 14, f"arista-leaf{L}", size=12, fill="#0f172a", weight="700"))
HOST_META = {"h1": ("10.110.0.11", "BD-A"), "h2": ("10.120.0.12", "BD-B"),
             "h3": ("10.110.0.13", "BD-A"), "h4": ("10.120.0.14", "BD-B")}
for host, hcx in HOST_CX.items():
    add(place_icon(ICON_HOST, f"svg-img-{host}", HOST_FILL, hcx, Y_HOST, S_HOST))
    ip, bd = HOST_META[host]
    add(text(hcx, Y_HOST + S_HOST/2 + 13, f"{host} · {bd}", size=11, fill="#334155", weight="700"))
    add(text(hcx, Y_HOST + S_HOST/2 + 26, ip, size=9, fill="#94a3b8", weight="600"))

# port-fills (over icons)
svg += ports_svg

# legend
lx, ly = 80, H - 18
add(text(lx, ly - 13, "link rate:", size=12, fill="#475569", weight="700", anchor="start"))
xx = lx + 8
for col, lab in [("#bec8d2", "idle"), ("#4BDD33", "active"), ("#FFFF00", "busy"), ("#FF8000", "hot"), ("#FF3154", "max/down")]:
    add(f'<rect x="{xx}" y="{ly-10}" width="22" height="10" rx="2" fill="{col}" stroke="#475569" stroke-width="0.5"/>')
    add(text(xx + 26, ly, lab, size=11, fill="#475569", weight="500", anchor="start"))
    xx += 26 + 12 + len(lab) * 7
add(text(W - 80, ly, "→ each link = 2 directional halves · arrow = egress · label = live bps", size=11,
         fill="#94a3b8", weight="500", anchor="end"))
add('</svg>')
SVG = "\n".join(svg)

# ---- panelConfig ----------------------------------------------------------
pc = ["---", "anchors:",
      "  thresholds-operstate: &thresholds-operstate",
      '    - { color: "#FF3154", level: 0 }',
      '    - { color: "#4BDD33", level: 1 }',
      "  thresholds-traffic: &thresholds-traffic",
      '    - { color: "#bec8d2", level: 0 }',
      '    - { color: "#4BDD33", level: 1000 }',
      '    - { color: "#FFFF00", level: 500000 }',
      '    - { color: "#FF8000", level: 2000000 }',
      '    - { color: "#FF3154", level: 8000000 }',
      "  label-config: &label-config",
      "    separator: replace", "    units: bps", "    decimalPoints: 0",
      "", "cellIdPreamble: cell-", "cells:"]
seen = set()
for cid, dref, kind in cells:
    if cid in seen:
        continue
    seen.add(cid)
    if kind == "traffic":
        pc += [f'  "{cid}":', f"    dataRef: {dref}", "    label: *label-config",
               "    strokeColor:", "      thresholds: *thresholds-traffic"]
    else:
        pc += [f'  "{cid}":', f"    dataRef: {dref}", "    fillColor:", "      thresholds: *thresholds-operstate"]
PANELCONFIG = "\n".join(pc) + "\n"

open(os.path.join(HERE, "topology.svg"), "w").write(SVG)
open(os.path.join(HERE, "panelConfig.yaml"), "w").write(PANELCONFIG)
nlinks = len([1 for c in seen if c.startswith("link_id:")])
nports = len([1 for c in seen if not c.startswith("link_id:")])
print(f"SVG bytes: {len(SVG)}  cells: {len(seen)}  half-links: {nlinks}  port-fills: {nports}")
