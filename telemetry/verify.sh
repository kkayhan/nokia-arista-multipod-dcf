#!/usr/bin/env bash
# Post-deploy verification for the nokia-arista-multipod-dcf telemetry stack.
set +e
PROM=http://localhost:9090
q() { curl -s "$PROM/api/v1/query" --data-urlencode "query=$1"; }
names() { curl -s "$PROM/api/v1/label/__name__/values"; }

echo "===== 1. containers ====="
sudo docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'gnmic|prometheus|grafana|promtail|loki' | sort

echo; echo "===== 2. prometheus target (gnmic) ====="
curl -s "$PROM/api/v1/targets" | python3 -c "import json,sys; d=json.load(sys.stdin); [print(t['labels'],t['health'],t.get('lastError','')) for t in d['data']['activeTargets']]"

echo; echo "===== 3. SR Linux interface_oper_state (sample) ====="
q 'interface_oper_state' | python3 -c "import json,sys; d=json.load(sys.stdin)['data']['result']; print('series:',len(d)); [print(' ',r['metric'].get('source'),r['metric'].get('interface_name'),r['value'][1]) for r in d[:6]]"

echo; echo "===== 4. Arista OpenConfig metric NAMES present ====="
names | python3 -c "import json,sys; v=json.load(sys.stdin)['data']; [print(' ',n) for n in v if n.startswith('interfaces_interface') or 'bgp_neighbors' in n or n.startswith('network_instances')]"

echo; echo "===== 5. Arista oper-status series + interface_name VALUES ====="
q 'interfaces_interface_state_oper_status' | python3 -c "import json,sys; d=json.load(sys.stdin)['data']['result']; print('series:',len(d)); [print(' ',r['metric'].get('source'),repr(r['metric'].get('interface_name')),r['value'][1]) for r in d[:8]]"

echo; echo "===== 6. Arista out_octets rate present? ====="
q 'rate(interfaces_interface_state_counters_out_octets[1m])*8' | python3 -c "import json,sys; d=json.load(sys.stdin)['data']['result']; print('series:',len(d)); [print(' ',r['metric'].get('source'),r['metric'].get('interface_name'),round(float(r['value'][1]),1),'bps') for r in d[:6]]"

echo; echo "===== 7. Arista BGP session-state ====="
q 'network_instances_network_instance_protocols_protocol_bgp_neighbors_neighbor_state_session_state' | python3 -c "import json,sys; d=json.load(sys.stdin)['data']['result']; print('series:',len(d)); [print(' ',r['metric'].get('source'),r['value'][1]) for r in d[:6]]" 2>/dev/null || echo "  (none / name differs)"

echo; echo "===== 8. datasource UIDs ====="
curl -s http://localhost:3000/api/datasources 2>/dev/null | python3 -c "import json,sys; [print(' ',x['type'],x['uid'],x['name']) for x in json.load(sys.stdin)]" 2>/dev/null || echo "  grafana not ready"

echo; echo "===== 9. Loki syslog sources ====="
curl -s "http://localhost:3100/loki/api/v1/label/source/values" 2>/dev/null || echo "  loki not ready"
