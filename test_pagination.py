import importlib.util, json
spec = importlib.util.spec_from_file_location("m", "RN-SPN-NAME-N-IP.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

test_tenant_id = "1351248577"
scoped_token = m.get_token(scope_tsg_id=test_tenant_id)

headers = {
    'Authorization': f'Bearer {scoped_token}',
    'Content-Type': 'application/json',
}
import requests
url = f"{m.BASE_URL}/config/deployment/v1/remote-networks?folder=Remote Networks"
resp = requests.get(url, headers=headers, verify=m.VERIFY_SSL)
body = resp.json()
print("offset:", body.get('offset'))
print("total:", body.get('total'))
print("limit:", body.get('limit'))
print("len(data):", len(body.get('data', [])))

# Check for ecmp_tunnels structure more broadly - count how many RNs use ecmp vs single tunnel
single = 0
ecmp = 0
for rn in body.get('data', []):
    if rn.get('ecmp_tunnels'):
        ecmp += 1
    elif rn.get('ipsec_tunnel'):
        single += 1
    else:
        print("RN with neither ipsec_tunnel nor ecmp_tunnels:", rn.get('name'))
print(f"single-tunnel RNs: {single}, ecmp RNs: {ecmp}")
