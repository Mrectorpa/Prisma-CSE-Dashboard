import importlib.util, json
spec = importlib.util.spec_from_file_location("m", "RN-SPN-NAME-N-IP.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

test_tenant_id = "1351248577"
scoped_token = m.get_token(scope_tsg_id=test_tenant_id)
rns = m.get_remote_networks(scoped_token, test_tenant_id)
print(f"Total remote networks: {len(rns)}")
if rns:
    print("=== FULL FIRST RECORD ===")
    print(json.dumps(rns[0], indent=2))
    print("=== ALL TOP-LEVEL KEYS ACROSS FIRST 5 RECORDS ===")
    keys = set()
    for rn in rns[:5]:
        keys.update(rn.keys())
    print(sorted(keys))

    print("=== RECORD WITH ecmp_tunnels (if any) ===")
    for rn in rns:
        if rn.get('ecmp_tunnels'):
            print(json.dumps(rn, indent=2))
            break
    else:
        print("No record with non-empty ecmp_tunnels found in this tenant's data")

    print("=== RECORD WITH subnets (if any) ===")
    for rn in rns:
        if rn.get('subnets'):
            print(json.dumps({k: rn[k] for k in ('name','subnets')}, indent=2))
            break
    else:
        print("No record with non-empty subnets found")

    print("=== service_ip_address presence check across all records ===")
    missing = [rn.get('name') for rn in rns if not rn.get('details', {}).get('service_ip_address')]
    print(f"Records missing details.service_ip_address: {len(missing)} / {len(rns)}")
    print(f"Sample missing: {missing[:5]}")
