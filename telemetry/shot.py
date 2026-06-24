#!/usr/bin/env python3
"""Screenshot a Grafana panel/dashboard from localhost:3000 (anonymous-admin)."""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else \
    "http://localhost:3000/d/nokia-arista-multipod-dcf/_?viewPanel=1&kiosk&theme=light"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/home/kkayhan/nokia-arista-multipod-dcf/telemetry/grafana.png"
W = int(sys.argv[3]) if len(sys.argv) > 3 else 1820
Hh = int(sys.argv[4]) if len(sys.argv) > 4 else 1000

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": W, "height": Hh}, device_scale_factor=1)
    pg.goto(URL, wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(9000)
    pg.screenshot(path=OUT)
    b.close()
print("wrote", OUT)
