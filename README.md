# nokia-arista-multipod-dcf

A multi-vendor EVPN-VXLAN data-center fabric you can run with [containerlab](https://containerlab.dev). Two leaf-spine pods — one **Nokia SR Linux**, one **Arista cEOS** — are joined into a single stretched overlay, so four hosts spread across both vendors reach each other over L2 and L3. A **Grafana telemetry dashboard** ships with the lab and lights up the whole fabric live.

![topology](grafana-topology.png)

## What you'll see

- A **single EVPN-VXLAN network spanning two different vendors** (Nokia SR Linux + Arista cEOS), interoperating purely over open standards — IS-IS, BGP-EVPN, VXLAN.
- **Two stretched L2 services** (BD-A and BD-B) plus a **tenant L3 VRF** that routes between them, so hosts in different pods and different subnets all talk to each other.
- **Two multihoming styles side by side** — EVPN **ESI all-active** on the Nokia side, **MLAG** on the Arista side — both transparently interworking under the same overlay.
- A **live topology dashboard** in Grafana showing per-link traffic and interface state across both pods in real time.

## Topology

Two pods, each a 2-spine / 4-leaf design, joined by a 4-link spine-to-spine mesh.

| Node | Vendor | Role |
|---|---|---|
| `nokia-spine1`, `nokia-spine2` | SR Linux | Spines — pure transit (no BGP) |
| `nokia-leaf1`…`nokia-leaf4` | SR Linux | Leaves / VTEPs (ESI multihoming) |
| `arista-spine1`, `arista-spine2` | cEOS | Spines — EVPN Route-Reflectors |
| `arista-leaf5`…`arista-leaf8` | cEOS | Leaves / VTEPs (MLAG multihoming) |
| `h1`…`h4` | Linux | Dual-homed test hosts |

The four hosts each bond two links to a leaf pair and sit on two stretched subnets:

| Host | IP | Service | Attached to |
|---|---|---|---|
| `h1` | 10.110.0.11 | BD-A | `nokia-leaf1` + `nokia-leaf2` (ESI) |
| `h2` | 10.120.0.12 | BD-B | `nokia-leaf3` + `nokia-leaf4` (ESI) |
| `h3` | 10.110.0.13 | BD-A | `arista-leaf5` + `arista-leaf6` (MLAG) |
| `h4` | 10.120.0.14 | BD-B | `arista-leaf7` + `arista-leaf8` (MLAG) |

## Requirements

| Component | Version | Notes |
|---|---|---|
| containerlab | 0.7x (tested 0.75.0) | the only thing you install |
| Nokia SR Linux | `ghcr.io/nokia/srlinux:26.3.2` | pulls automatically |
| network-multitool | `ghcr.io/srl-labs/network-multitool:latest` | pulls automatically (the hosts) |
| Arista cEOS | `ceos:4.34.2.1F` | **you must import this manually** ↓ |
| Grafana / Prometheus / Loki / gnmic / Promtail | pinned in the topology file | pull automatically (telemetry stack) |

> **cEOS is not downloadable from a public registry.** Get `cEOS64-lab-4.34.2.1F.tar.xz` from your Arista account, then import it so the `ceos:4.34.2.1F` tag exists:
> ```bash
> docker import cEOS64-lab-4.34.2.1F.tar.xz ceos:4.34.2.1F
> ```

Also make sure these host ports are free, they're used by the dashboard: **3000** (Grafana), **9090** (Prometheus), **3100** (Loki), **9080** (Promtail).

## Deploy

```bash
sudo containerlab deploy -t nokia-arista-multipod-dcf.clab.yaml
```

> **Give it ~90 seconds to settle.** On boot every switch holds itself out of the forwarding path for 90 s (the IS-IS overload timer) while the fabric converges. A ping run immediately after deploy may fail — wait it out, then everything works.

Tear it down with:
```bash
sudo containerlab destroy -t nokia-arista-multipod-dcf.clab.yaml
```

## Watch it live — Grafana dashboard

Once deployed, open **http://localhost:3000** in your browser. No login is needed and the dashboard loads automatically.

**The topology panel** at the top is the centerpiece. It draws the whole fabric and animates it:
- Every link is split into **two halves**, one per direction, each with an **arrow** (the way traffic is leaving) and a **live throughput number**.
- Link **colour tracks load** — grey when idle, green when active, up to red when busy.
- The little squares at each interface are **green when the port is up**, red when down.
- **Blue = Nokia, teal = Arista.** Both pods light up, including the links crossing between them.

Below the map are per-switch panels — throughput, BGP-EVPN sessions, CPU, memory, service state, and a log viewer. Use the **node selector** at the top of the dashboard to focus those panels on any switch.

### Make traffic flow

The map only moves when packets are flowing. A simple interactive tool drives test traffic between the four hosts:

```bash
sudo python3 traffic.py
```

Pick a scenario — each one is labelled with the service it exercises:

| Scenario | What it shows |
|---|---|
| BD-A L2 stretch, cross-site (h1↔h3) | Same subnet, Nokia ↔ Arista over the L2 overlay |
| BD-B L2 stretch, cross-site (h2↔h4) | Same subnet, the other bridge domain |
| BD-A↔BD-B routed, Nokia-local (h1↔h2) | Routed between subnets inside one pod |
| BD-A↔BD-B routed, Arista-local (h3↔h4) | Routed between subnets inside the other pod |
| BD-A↔BD-B, cross-site (h1↔h4, h3↔h2) | Routed **and** across pods |
| Full mesh | All host pairs at once |

Set the rate, then watch the per-host throughput table in the tool and the links light up in Grafana. Press **`s`** to stop all traffic, **`q`** to quit (traffic keeps running until you stop it).

### Logs

Open the **log viewer** panel (pick a node with the selector) to browse device syslog — config changes, interface flaps, protocol events.

> **Note:** SR Linux (Nokia) logs flow fully into the dashboard. Arista cEOS logs do **not** appear — the containerized cEOS lab image stops sending syslog after it boots. This is a limitation of the cEOS image, not the lab; the syslog config is correct and works on real EOS hardware. Everything else for the Arista pod — metrics, link state, the topology map — works fully.

## Explore the fabric

Run these after the ~90 s settle time.

### Do the hosts all reach each other?

The four test hosts are plain Linux containers — drive them with `docker exec` (prefix `sudo` if your Docker needs it):
```bash
for s in h1 h2 h3 h4; do
  for d in 10.110.0.11 10.120.0.12 10.110.0.13 10.120.0.14; do
    docker exec "$s" ping -c2 -W2 "$d"
  done
done
```
All pings should succeed — same-subnet (L2 stretch) and across subnets (routed). Drop into a host's shell with `docker exec -it h1 bash`.

### Log into the switches over SSH

containerlab adds each switch's name to your `/etc/hosts`, so you can SSH to them by name:

```bash
ssh admin@nokia-leaf1      # Nokia SR Linux  →  password: NokiaSrl1!
ssh admin@arista-leaf5     # Arista cEOS     →  password: admin
```

Run a single command without logging in interactively:
```bash
ssh admin@arista-spine1 "show bgp evpn summary"
```

> On redeploy the switches get new SSH host keys. If SSH warns about a changed key, clear the old one with `ssh-keygen -R nokia-leaf1`, or add `-o StrictHostKeyChecking=no`.

### Useful `show` commands

**Nokia SR Linux** — `ssh admin@nokia-spine1` (or `nokia-leaf1`…`nokia-leaf4`):

| On | Command | Shows |
|---|---|---|
| spine | `show network-instance default protocols isis adjacency` | IS-IS neighbors (local leaves + the Arista spines) |
| leaf | `show network-instance default protocols bgp neighbor` | BGP-EVPN sessions to the route-reflectors |
| leaf | `show system network-instance ethernet-segments` | ESI all-active state / designated forwarder |
| leaf | `show network-instance bd-a bridge-table mac-table all` | learned MACs in BD-A (local + remote VTEPs) |
| leaf | `show tunnel vxlan-tunnel all` | remote VTEPs this leaf talks to |

**Arista cEOS** — `ssh admin@arista-spine1` (or `arista-leaf5`…`arista-leaf8`):

| On | Command | Shows |
|---|---|---|
| spine | `show bgp evpn summary` | route-reflector sessions (expect 9 established) |
| spine / leaf | `show isis neighbors` | IS-IS neighbors |
| leaf | `show mlag` | MLAG health (state `Active`, peer-link `Up`) |
| leaf | `show vxlan vtep` | remote VTEPs |
| leaf | `show bgp evpn summary` | EVPN sessions to both route-reflectors |

## How the fabric works (reference)

**Services.** Two L2 bridge domains are stretched across both pods, and a tenant L3 VRF routes between them. All four hosts share one anycast gateway MAC on every leaf, both vendors.

| Service | Subnet | Gateway | Hosts |
|---|---|---|---|
| BD-A | 10.110.0.0/24 | 10.110.0.1 | h1, h3 |
| BD-B | 10.120.0.0/24 | 10.120.0.1 | h2, h4 |
| Tenant VRF | routes BD-A ↔ BD-B (symmetric IRB) | — | all |

**Loopbacks & areas.** Each pod is its own IS-IS area; loopbacks are reachable end to end with no route leaking.

| | Nokia pod | Arista pod |
|---|---|---|
| IS-IS area | 49.0200 | 49.0078 |
| Loopbacks | 10.252.200.x | 10.252.183.x |

**Underlay** — a multi-area IS-IS fabric. Each pod is one area; the pods join over a Level-2-only spine-to-spine mesh, IPv4-only, jumbo MTU. (Cross-vendor IS-IS needs matched MTU, same-subnet /31s, and loosened hello padding on the inter-pod links — already configured here.)

**Overlay** — one iBGP-EVPN domain, ASN 65524 everywhere. The two **Arista spines are the EVPN route-reflectors** for all eight leaves in both pods; the Nokia spines run no BGP and are pure transit. Only the leaves are VTEPs.

**Multihoming** — each host dual-homes to a leaf pair, but each pod does it its own way and they interwork because only standard EVPN crosses between pods:

| | Nokia pod | Arista pod |
|---|---|---|
| Method | EVPN ESI, all-active | MLAG |
| Pairs | leaf1+leaf2, leaf3+leaf4 | leaf5+leaf6, leaf7+leaf8 |
| Peer-link | none needed | `Port-Channel1` (Ethernet4+5) |

## What's in the repo

```
nokia-arista-multipod-dcf.clab.yaml   # the lab — switches, hosts, telemetry stack
traffic.py                            # interactive traffic generator
configs/                              # per-device startup configs + the telemetry stack config
telemetry/                            # tooling used to build the dashboard (you don't need to touch this)
```
