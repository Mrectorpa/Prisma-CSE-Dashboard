import importlib.util
spec = importlib.util.spec_from_file_location("m", "RN-SPN-NAME-N-IP.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.verbose_enabled = True

tenant_id = "1351248577"
token = m.get_token(scope_tsg_id=tenant_id)
if not token:
    print("Could not get token")
    raise SystemExit(1)

bw_map = m.get_tunnel_bandwidth_map(token, tenant_id)
print(f"Sites in bandwidth map: {len(bw_map)}")

for site in ["USDRHRT01", "BLV-ECMP", "ACD-ECMP"]:
    if site in bw_map:
        avg_kbps, peak_kbps = bw_map[site]
        avg_display = m.format_bandwidth_value(avg_kbps)
        peak_display = m.format_bandwidth_value(peak_kbps)
        print(f"{site}: raw avg_kbps={avg_kbps}, raw peak_kbps={peak_kbps} -> Avg={avg_display}, Peak={peak_display}")
    else:
        print(f"{site}: NOT FOUND in map")
