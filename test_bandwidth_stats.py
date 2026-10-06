"""
test_bandwidth_stats.py
------------------------
Standalone live verification harness for get_bandwidth_stats() in
RN-SPN-NAME-N-IP.py. Uses its OWN static CLIENT_ID / CLIENT_SECRET /
TSG_ID (set below) to mint tokens directly -- independent of whatever is
currently configured in RN-SPN-NAME-N-IP.py -- so this script can be run
repeatedly without needing to edit the main script's placeholder creds
each time.

Mints a FRESH tenant-scoped token immediately before EACH call (with a
short delay between attempts) to rule out gateway flakiness/rate-limiting
as the cause of intermittent 401/403/500 errors previously observed when
reusing a single token across rapid requests.

FILL IN BEFORE RUNNING:
    CLIENT_ID, CLIENT_SECRET, TSG_ID (root/MSP TSG), TEST_TENANT_ID (a
    child tenant under that TSG with at least one remote network).
"""
import json
import time
import requests
import urllib3

# --- Static credentials (fill in before running) ---
CLIENT_ID = "mrector-svc-account@1602436186.iam.panserviceaccount.com"
CLIENT_SECRET = "3dd627be-4289-4ed0-af96-9029d46a17ff"
TSG_ID = "1602436186"
TEST_TENANT_ID = "1351248577"

AUTH_URL = "https://auth.apps.paloaltonetworks.com/am/oauth2/access_token"
BASE_URL = "https://api.sase.paloaltonetworks.com"
REGION = "americas"
VERIFY_SSL = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_token(scope_tsg_id):
    payload = {
        'grant_type': 'client_credentials',
        'scope': f'tsg_id:{scope_tsg_id}'
    }
    resp = requests.post(AUTH_URL, data=payload, auth=(CLIENT_ID, CLIENT_SECRET), verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json()['access_token']


def get_remote_networks(tenant_tsg_id):
    token = get_token(tenant_tsg_id)
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    all_data = []
    offset = 0
    while True:
        url = f"{BASE_URL}/config/deployment/v1/remote-networks?folder=Remote Networks&limit=200&offset={offset}"
        resp = requests.get(url, headers=headers, verify=VERIFY_SSL)
        if resp.status_code != 200:
            break
        body = resp.json()
        page = body.get('data', [])
        all_data.extend(page)
        total = body.get('total', len(all_data))
        offset += len(page)
        if not page or offset >= total:
            break
    return all_data


def try_call(label, filter_rules, filter_operator=None, extra_payload=None, delay=2,
              use_region_header=False, use_tenant_header=False, enable_empty_interval=False):
    time.sleep(delay)
    fresh_token = get_token(TEST_TENANT_ID)

    url = f"{BASE_URL}/insights/v3.0/resource/query/sites/bandwidth_consumption_histogram"
    filter_obj = {"rules": filter_rules}
    if filter_operator:
        filter_obj["operator"] = filter_operator
    histogram_obj = {
        "property": "event_time",
        "range": "minute",
        "value": 30
    }
    if enable_empty_interval:
        histogram_obj["enableEmptyInterval"] = True
    payload = {
        "filter": filter_obj,
        "histogram": histogram_obj
    }
    if extra_payload:
        payload.update(extra_payload)

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + fresh_token,
    }
    if use_region_header:
        headers['PANW-Region'] = REGION
    if use_tenant_header:
        headers['Prisma-Tenant'] = str(TEST_TENANT_ID)

    print(f"\n=== ATTEMPT: {label} ===")
    print(f"Headers (excl Authorization): { {k: v for k, v in headers.items() if k != 'Authorization'} }")
    print("Payload: " + json.dumps(payload))
    resp = requests.post(url, headers=headers, json=payload, verify=VERIFY_SSL)
    print(f"Status: {resp.status_code}")
    try:
        body = resp.json()
        data = body.get('data', [])
        print(f"Bucket count: {len(data)}")
        if data:
            print("First bucket:")
            print(json.dumps(data[0], indent=2))
        else:
            print("Full body:")
            print(json.dumps(body, indent=2)[:1000])
    except Exception as e:
        print(f"Could not parse JSON: {e}")
        print(resp.text[:800])


print("[*] Fetching remote networks to find a real site name...")
rns = get_remote_networks(TEST_TENANT_ID)
if not rns:
    print("[!] No remote networks found for this tenant. Aborting.")
    raise SystemExit(1)

site_name = rns[0].get('name')
print(f"[*] Using site_name='{site_name}' for bandwidth test")

# Exact combo from the confirmed-working browser-captured example:
# NO PANW-Region / Prisma-Tenant headers, NO enableEmptyInterval,
# site_name filter uses operator "in", NO top-level filter.operator key.
try_call("EXACT working combo: no region/tenant headers, site_name/in, no enableEmptyInterval",
         filter_rules=[
             {"operator": "last_n_days", "property": "event_time", "values": [30]},
             {"operator": "in", "property": "site_name", "values": [site_name]}
         ],
         use_region_header=False, use_tenant_header=False, enable_empty_interval=False)

# Sanity re-check: same combo WITH the headers, to confirm headers are what breaks it.
try_call("Same filter WITH PANW-Region + Prisma-Tenant headers (regression check)",
         filter_rules=[
             {"operator": "last_n_days", "property": "event_time", "values": [30]},
             {"operator": "in", "property": "site_name", "values": [site_name]}
         ],
         use_region_header=True, use_tenant_header=True, enable_empty_interval=False)
