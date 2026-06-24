#!/usr/bin/env python3
"""
Interactive traffic generator for nokia-arista-multipod-dcf.

Drives iperf (UDP) between the four dual-homed Linux hosts so the Grafana flow
panel lights up. Every scenario is labelled with the EVPN service it exercises:

  Host  IP             BD     Subnet           Pod / multihoming
  h1    10.110.0.11    BD-A   10.110.0.0/24    Nokia  (ESI all-active, leaf1/2)
  h2    10.120.0.12    BD-B   10.120.0.0/24    Nokia  (ESI all-active, leaf3/4)
  h3    10.110.0.13    BD-A   10.110.0.0/24    Arista (MLAG, leaf5/6)
  h4    10.120.0.14    BD-B   10.120.0.0/24    Arista (MLAG, leaf7/8)

  same BD  -> pure L2 EVPN (VXLAN bridge, VNI 10110/10120)
  diff BD  -> L3 routed in tenant VRF via symmetric IRB (L3 VNI 50001)
  Nokia<->Arista -> traffic crosses the inter-pod IS-IS L2 backbone (cross-site)

Run:  sudo python3 traffic.py     (lab must be deployed)
"""
import subprocess, sys, time, os, select, termios, tty
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- host model -----------------------------------------------------------
HOSTS = {
    "h1": {"ip": "10.110.0.11", "bd": "BD-A", "pod": "Nokia"},
    "h2": {"ip": "10.120.0.12", "bd": "BD-B", "pod": "Nokia"},
    "h3": {"ip": "10.110.0.13", "bd": "BD-A", "pod": "Arista"},
    "h4": {"ip": "10.120.0.14", "bd": "BD-B", "pod": "Arista"},
}
NODES = list(HOSTS)
IFACE = "bond0"
BASE_PORT = 5201


def service_of(a, b):
    """Describe the EVPN service + site span a<->b traffic traverses."""
    same_bd = HOSTS[a]["bd"] == HOSTS[b]["bd"]
    cross = HOSTS[a]["pod"] != HOSTS[b]["pod"]
    svc = (f"L2 EVPN stretch {HOSTS[a]['bd']} (VNI {'10110' if HOSTS[a]['bd']=='BD-A' else '10120'})"
           if same_bd else "L3 inter-VRF (tenant, L3 VNI 50001, symmetric IRB)")
    span = "cross-site (Nokia↔Arista)" if cross else f"intra-site ({HOSTS[a]['pod']})"
    return f"{svc} · {span}"


# pair = (a, b); traffic is generated in BOTH directions
SCENARIOS = {
    "1": ("BD-A L2 stretch, cross-site", [("h1", "h3")]),
    "2": ("BD-B L2 stretch, cross-site", [("h2", "h4")]),
    "3": ("BD-A↔BD-B L3 routed, Nokia-local", [("h1", "h2")]),
    "4": ("BD-A↔BD-B L3 routed, Arista-local", [("h3", "h4")]),
    "5": ("BD-A↔BD-B L3, cross-site", [("h1", "h4"), ("h3", "h2")]),
    "6": ("Full mesh (all 6 host pairs)",
          [("h1", "h2"), ("h1", "h3"), ("h1", "h4"), ("h2", "h3"), ("h2", "h4"), ("h3", "h4")]),
}

# ---- docker plumbing ------------------------------------------------------
def _docker_base():
    if subprocess.run(["docker", "ps"], capture_output=True).returncode == 0:
        return ["docker"]
    if subprocess.run(["sudo", "-n", "docker", "ps"], capture_output=True).returncode == 0:
        return ["sudo", "docker"]
    sys.exit("ERROR: cannot run docker. Re-run as 'sudo python3 traffic.py'.")


DOCKER = _docker_base()


def discover():
    """Map clab node name -> container name (prefix-agnostic)."""
    r = subprocess.run(DOCKER + ["ps", "--format", '{{.Names}}\t{{.Label "clab-node-name"}}'],
                       capture_output=True, text=True)
    n2c = {}
    for line in r.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1]:
            n2c[parts[1]] = parts[0]
    missing = [n for n in NODES if n not in n2c]
    if missing:
        sys.exit(f"ERROR: host container(s) not found: {missing}. Is the lab deployed?")
    return {n: n2c[n] for n in NODES}


CONT = discover()


def run(node, cmd):
    return subprocess.run(DOCKER + ["exec", CONT[node], "bash", "-c", cmd],
                          capture_output=True, text=True)


def run_bulk(tasks):
    out = []
    with ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
        futs = {pool.submit(run, n, c): n for n, c in tasks}
        for f in as_completed(futs):
            out.append(f.result())
    return out


# ---- traffic control ------------------------------------------------------
def stop():
    run_bulk([(n, "killall -q iperf iperf3 2>/dev/null; true") for n in NODES])


def start(pairs, bw_mbps, flows):
    stop()
    time.sleep(0.5)
    # one server port per (pair, flow); same port used on both endpoints
    plan = []   # (src, dst_ip, port, bw)
    servers = {}  # node -> set(ports)
    port = BASE_PORT
    bw_per = bw_mbps / max(1, flows)
    for a, b in pairs:
        for src, dst in ((a, b), (b, a)):          # both directions
            for _ in range(flows):
                servers.setdefault(dst, set()).add(port)
                plan.append((src, HOSTS[dst]["ip"], port, bw_per))
                port += 1
    # start servers
    stasks = []
    for node, ports in servers.items():
        c = "; ".join(f"iperf -s -u -p {p} -D" for p in sorted(ports))
        stasks.append((node, c))
    run_bulk(stasks)
    time.sleep(0.8)
    # start clients (detached, long-running)
    ctasks = {}
    for src, dst_ip, p, bw in plan:
        c = (f"setsid sh -c 'iperf -c {dst_ip} -u -p {p} -b {bw:.2f}M -t 86400 "
             f">/dev/null 2>&1' &")
        ctasks.setdefault(src, []).append(c)
    run_bulk([(n, " ".join(cs)) for n, cs in ctasks.items()])


def iperf_running():
    # `pgrep -c iperf` prints the count but exits 1 when zero, so avoid `|| echo`
    # (that yields "0\n0"). Take the first numeric token, default 0.
    res = run_bulk([(n, "pgrep -c iperf 2>/dev/null; true") for n in NODES])
    total = 0
    for r in res:
        toks = r.stdout.split()
        total += int(toks[0]) if toks and toks[0].isdigit() else 0
    return total


# ---- live monitor ---------------------------------------------------------
def read_counters():
    out = {}
    def one(n):
        rr = run(n, f"cat /sys/class/net/{IFACE}/statistics/rx_bytes "
                    f"/sys/class/net/{IFACE}/statistics/tx_bytes 2>/dev/null")
        try:
            rx, tx = [int(x) for x in rr.stdout.split()]
        except Exception:
            rx, tx = 0, 0
        return n, (rx, tx)
    with ThreadPoolExecutor(max_workers=len(NODES)) as pool:
        for n, v in pool.map(one, NODES):
            out[n] = v
    return out


def monitor_table(prev, prev_t):
    cur = read_counters()
    t = time.time()
    dt = max(1e-6, t - prev_t)
    lines = ["=" * 64,
             f"  {'host':<6}{'BD':<6}{'pod':<8}{'rx (Mb/s)':>12}{'tx (Mb/s)':>12}",
             "-" * 64]
    trx = ttx = 0.0
    for n in NODES:
        prx, ptx = prev.get(n, (0, 0))
        crx, ctx = cur.get(n, (0, 0))
        rxr = (crx - prx) * 8 / dt / 1e6
        txr = (ctx - ptx) * 8 / dt / 1e6
        trx += rxr; ttx += txr
        lines.append(f"  {n:<6}{HOSTS[n]['bd']:<6}{HOSTS[n]['pod']:<8}{rxr:>12.2f}{txr:>12.2f}")
    lines += ["-" * 64, f"  {'TOTAL':<20}{trx:>12.2f}{ttx:>12.2f}", "=" * 64]
    return lines, cur, t


# ---- UI -------------------------------------------------------------------
def print_menu(msg, running):
    os.system("clear")
    print("===== nokia-arista-multipod-dcf  ·  traffic generator =====")
    print(f"  hosts: " + "  ".join(f"{n}({HOSTS[n]['ip']},{HOSTS[n]['bd']},{HOSTS[n]['pod']})" for n in NODES))
    print(f"  iperf processes running: {running}")
    print()
    for k, (name, _) in SCENARIOS.items():
        print(f"   {k}) {name}")
    print("   c) Custom src->dst")
    print("   s) Stop all traffic")
    print("   r) Refresh")
    print("   q) Quit")
    if msg:
        print(f"\n  >> {msg}")
    print("\n  choose: ", end="", flush=True)


def ask(prompt, old):
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
    try:
        return input(prompt).strip()
    finally:
        tty.setcbreak(sys.stdin.fileno())


def launch(pairs, old):
    print()
    for a, b in pairs:
        print(f"   {a} <-> {b}: {service_of(a, b)}")
    try:
        bw = float(ask("\n  total bandwidth per direction (Mb/s) [10]: ", old) or "10")
        flows = int(ask("  parallel flows per direction [1]: ", old) or "1")
    except ValueError:
        return "invalid number"
    start(pairs, bw, flows)
    return f"started {len(pairs)} pair(s) bidirectional @ {bw:.0f} Mb/s x{flows} flow(s)"


def main():
    prev = read_counters(); prev_t = time.time(); msg = "ready"
    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            tbl, prev, prev_t = monitor_table(prev, prev_t)
            running = iperf_running()
            print_menu(msg, running)
            print("\n" + "\n".join(tbl))
            print("\n  choose: ", end="", flush=True)
            ready, _, _ = select.select([sys.stdin], [], [], 1.5)
            if not ready:
                continue
            k = sys.stdin.read(1)
            if k in SCENARIOS:
                msg = launch(SCENARIOS[k][1], old)
            elif k == "c":
                a = ask("\n  source host (h1-h4): ", old)
                b = ask("  dest host   (h1-h4): ", old)
                if a in HOSTS and b in HOSTS and a != b:
                    msg = launch([(a, b)], old)
                else:
                    msg = "invalid host pair"
            elif k == "s":
                stop(); msg = "stopped all traffic"
            elif k == "r":
                msg = "refreshed"
            elif k == "q":
                break
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        print("\nbye (traffic left running; choose 's' next time to stop).")


if __name__ == "__main__":
    main()
