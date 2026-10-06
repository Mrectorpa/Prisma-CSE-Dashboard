"""
RN-SPN-NAME-N-IP.py
--------------------
Exports Remote Networks and their IPSec tunnels for every child tenant under
an MSP/Panorama root TSG, including the Security Processing Node (SPN) name
and IP address serving each remote network.

HOW IT WORKS
    1. Mints a root-scoped OAuth2 token to discover all child tenants
       (via /tenancy/v1/tenant_service_groups).
    2. For EACH child tenant, mints a SEPARATE OAuth2 token scoped directly
       to that tenant (scope=tsg_id:<child_id>). This is required because
       the Prisma SASE config API scopes requests based on the tenant baked
       into the token at mint time -- NOT by a request header -- so a single
       root token cannot be reused across child tenants for config APIs.
    3. Calls /config/deployment/v1/remote-networks (with pagination) using
       each tenant-scoped token to retrieve that tenant's remote networks.
    4. The SPN IP address is read directly from each remote network record's
       embedded `details.service_ip_address` field. (An earlier approach
       tried to cross-reference a public SPN IP list from the GlobalProtect
       `getAddrList` API, but that API key is invalid for 2 of 3 regional
       endpoints and returns an empty list from the 3rd -- it is unreliable
       and unnecessary since the IP is already present in the config data.)
    5. Remote networks with multiple tunnels (ECMP) are expanded into one
       CSV row per tunnel; single-tunnel remote networks produce one row.
    6. Once per tenant, makes a SINGLE call to the Insights v3.0
       `tunnels/tunnel_list` API (30-day lookback, all tunnels in the
       tenant) reusing the same tenant-scoped token minted for the config
       API. Each row returned is one tunnel with pre-computed 30-day
       `avg_throughput` / `peak_throughput` figures (no manual histogram
       aggregation needed -- these are query-scoped, ready-to-use values).
       The response's `site_name` field matches the Remote Network Name
       used elsewhere in this script. Rows are grouped by `site_name` and
       summed (ECMP remote networks have multiple tunnel rows for the same
       site) to produce:
         - 30-Day Avg Bandwidth (Mbps): sum of avg_throughput across all
           tunnels for that site.
         - 30-Day Peak Bandwidth (Mbps): sum of peak_throughput across all
           tunnels for that site.
       NOTE: An earlier implementation used the
       `sites/bandwidth_consumption_histogram` API and manually averaged/
       maxed 30-minute buckets, but the resulting figures did not match
       Strata Cloud Manager's displayed bandwidth. `tunnels/tunnel_list`
       returns the same kind of pre-aggregated, query-scoped throughput
       values SCM's own UI is expected to use, and only requires ONE API
       call per tenant (vs. one call per remote network previously) --
       both more accurate and more efficient. See get_tunnel_bandwidth_map()
       for the UNVERIFIED unit-conversion assumption (Kbps -> Mbps) that
       should be confirmed against SCM if figures still look off by a
       factor of 1000.
    7. Writes everything to prisma_sase_inventory.csv.

NOTES ON BANDWIDTH DATA (lessons learned during implementation)
    Some child tenants may return `REST10005 "RBAC - Query Permission
    Denied"` for the tunnel_list endpoint even though the same
    tenant-scoped token works fine for the config API. This is an expected,
    legitimate per-tenant RBAC boundary (observed on a real run against the
    prior histogram-based approach: 15 of 50+ tenants were denied bandwidth
    query access while the rest succeeded) -- not a bug. The script handles
    this gracefully: affected tenants simply show "N/A" for both bandwidth
    columns across all their rows, while every other tenant populates
    normally. If a specific tenant's bandwidth data is needed, grant the
    service account Insights/Monitoring query permission for that tenant in
    the Prisma SASE IAM console.

REQUIRED CREDENTIALS (set below)
    CLIENT_ID       - SASE API service account client ID
    CLIENT_SECRET   - SASE API service account client secret
    TSG_ID          - Root/MSP TSG ID the service account authenticates against

USAGE
    python RN-SPN-NAME-N-IP.py [--verbose]

    --verbose   Print detailed per-request debug information (API calls,
                status codes, response previews). Off by default.

OUTPUT
    prisma_sase_inventory.csv in the current working directory, with columns:
    Tenant Name, Tenant ID, Remote Network Name, SPN Name, Region,
    IPSec Tunnel, SPN IP Address, 30-Day Avg Bandwidth (Mbps),
    30-Day Peak Bandwidth (Mbps)
"""
import requests
import csv
import sys
import argparse
import urllib3

# --- Configuration ---
BASE_URL = "https://api.sase.paloaltonetworks.com"
AUTH_URL = "https://auth.apps.paloaltonetworks.com/am/oauth2/access_token"

CLIENT_ID = "mrector-svc-account@1602436186.iam.panserviceaccount.com"
CLIENT_SECRET = "3dd627be-4289-4ed0-af96-9029d46a17ff"
TSG_ID = "1602436186"

# SSL Verification - Set to False if hitting "self-signed certificate" errors locally
VERIFY_SSL = False

# Region header is required for monitoring APIs (e.g., 'americas', 'europe', 'uk', 'sg')
REGION = "americas"

# Page size for the remote-networks config API (max observed/accepted: 200)
PAGE_LIMIT = 200

verbose_enabled = False

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def debug(msg):
    if verbose_enabled:
        print(f"[DEBUG] {msg}")


def get_token(scope_tsg_id=None):
    """Generates an OAuth2 token for SASE API access, scoped to the given
    TSG ID (defaults to the root TSG_ID if not provided)."""
    target_tsg = scope_tsg_id or TSG_ID
    try:
        payload = {
            'grant_type': 'client_credentials',
            'scope': f'tsg_id:{target_tsg}'
        }
        response = requests.post(AUTH_URL, data=payload, auth=(CLIENT_ID, CLIENT_SECRET), verify=VERIFY_SSL)
        response.raise_for_status()
        return response.json()['access_token']
    except Exception as e:
        print(f"[!] Authentication Failed (scope tsg_id:{target_tsg}): {e}")
        return None


def get_tenants(token):
    """Lists all child tenants using both Monitoring and Tenancy APIs as fallback."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'X-PANW-Region': REGION
    }

    # Attempt 1: Monitoring API
    try:
        url = f"{BASE_URL}/mt/monitor/v1/tenants"
        response = requests.get(url, headers=headers, verify=VERIFY_SSL)
        debug(f"get_tenants attempt1 url={url} status={response.status_code}")
        if response.status_code == 200:
            items = response.json().get('items', [])
            if items:
                return items
    except Exception as e:
        debug(f"get_tenants attempt1 EXCEPTION: {e}")

    # Attempt 2: Tenancy/TSG API (Fallback for discovery)
    try:
        url = f"{BASE_URL}/tenancy/v1/tenant_service_groups"
        response = requests.get(url, headers=headers, verify=VERIFY_SSL)
        debug(f"get_tenants attempt2 url={url} status={response.status_code}")
        response.raise_for_status()
        items = response.json().get('items', [])
        debug(f"get_tenants attempt2 returned {len(items)} items")
        return items
    except Exception as e:
        print(f"[!] Critical: Could not retrieve tenant list from any endpoint: {e}")
        return []


def get_remote_networks(tenant_tsg_id):
    """Retrieves ALL remote network configurations for a specific child
    tenant, paging through results as needed. Mints its own token scoped
    directly to this tenant, since the config API does not honor a header
    override of tenant scope on a token minted for a different TSG."""
    token = get_token(scope_tsg_id=tenant_tsg_id)
    if not token:
        print(f"[!] Could not obtain a scoped token for tenant {tenant_tsg_id}; skipping.")
        return []

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    all_data = []
    offset = 0
    while True:
        url = f"{BASE_URL}/config/deployment/v1/remote-networks?folder=Remote Networks&limit={PAGE_LIMIT}&offset={offset}"
        try:
            response = requests.get(url, headers=headers, verify=VERIFY_SSL)
            debug(f"get_remote_networks tenant={tenant_tsg_id} offset={offset} status={response.status_code}")
            if response.status_code != 200:
                debug(f"get_remote_networks tenant={tenant_tsg_id} non-200 body(first 300)={response.text[:300]}")
                break
            body = response.json()
            page_data = body.get('data', [])
            all_data.extend(page_data)
            total = body.get('total', len(all_data))
            offset += len(page_data)
            if not page_data or offset >= total:
                break
        except Exception as e:
            print(f"[!] Error retrieving remote networks for tenant {tenant_tsg_id} at offset {offset}: {e}")
            break

    debug(f"get_remote_networks tenant={tenant_tsg_id} returned {len(all_data)} total remote networks")
    return all_data


def format_bandwidth_value(value_kbps):
    """Formats a raw Kbps throughput value for display, matching Strata
    Cloud Manager's convention of showing sub-1-Mbps values in Kbps (with
    full precision) and larger values in Mbps. This avoids the precision
    loss that occurs when rounding small Kbps values to 2 decimal places
    in Mbps (e.g. 26.10 Kbps would round to 0.03 Mbps, losing most of its
    significant digits).

    Returns "N/A" if value_kbps is None."""
    if value_kbps is None:
        return "N/A"
    mbps = value_kbps / 1000
    if mbps < 1:
        return f"{value_kbps:.2f} Kbps"
    return f"{mbps:.2f} Mbps"


def get_tunnel_bandwidth_map(token, tenant_tsg_id):
    """Queries the Insights v3.0 tunnels/tunnel_list API ONCE for a tenant,
    covering the last 30 days, and returns a dict mapping each site_name
    (== Remote Network Name) to (avg_kbps, peak_kbps) RAW Kbps sums
    (NOT pre-converted to Mbps -- see format_bandwidth_value() for display
    formatting):
      - avg_kbps: sum of avg_throughput across all tunnel rows sharing that
        site_name (ECMP remote networks have multiple tunnel rows; summing
        approximates the combined-link throughput for the site).
      - peak_kbps: sum of peak_throughput across all tunnel rows sharing
        that site_name.
    This replaces an earlier histogram-based approach
    (bandwidth_consumption_histogram) whose computed values did not match
    Strata Cloud Manager's displayed figures. tunnel_list instead returns
    pre-computed, query-scoped 30-day avg/peak throughput per tunnel
    directly -- the same underlying data SCM's own UI is expected to use --
    and only requires ONE API call per tenant (covering every tunnel),
    rather than one call per remote network.

    UNIT ASSUMPTION (confirmed): avg_throughput / peak_throughput are in
    Kbps -- confirmed against SCM, which displayed 26.10 Kbps for USDRHRT01
    while this API returned a raw sum of ~26.1 for that site's avg_throughput.
    Values are kept as raw Kbps here and only converted/formatted for
    display in format_bandwidth_value(), to avoid losing precision on
    sub-1-Mbps values.

    Returns {} on any failure, so the caller can fall back to 'N/A' in the
    CSV output for every remote network in that tenant."""
    url = f"{BASE_URL}/insights/v3.0/resource/query/tunnels/tunnel_list"
    payload = {
        "filter": {
            "rules": [
                {
                    "operator": "last_n_days",
                    "property": "event_time",
                    "values": [30]
                }
            ]
        }
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'PANW-Region': REGION,
        'Prisma-Tenant': str(tenant_tsg_id),
        'Authorization': f'Bearer {token}',
    }

    try:
        response = requests.post(url, headers=headers, json=payload, verify=VERIFY_SSL)
        debug(f"get_tunnel_bandwidth_map tenant={tenant_tsg_id} status={response.status_code}")
        if response.status_code != 200:
            debug(f"get_tunnel_bandwidth_map tenant={tenant_tsg_id} non-200 body(first 300)={response.text[:300]}")
            return {}

        body = response.json()
        data = body.get('data', [])
        if not data:
            debug(f"get_tunnel_bandwidth_map tenant={tenant_tsg_id} returned no tunnel rows")
            return {}

        site_sums = {}
        for tunnel in data:
            site_name = tunnel.get('site_name')
            if not site_name:
                continue
            avg_throughput = tunnel.get('avg_throughput') or 0
            peak_throughput = tunnel.get('peak_throughput') or 0
            if site_name not in site_sums:
                site_sums[site_name] = {'avg': 0.0, 'peak': 0.0}
            site_sums[site_name]['avg'] += avg_throughput
            site_sums[site_name]['peak'] += peak_throughput

        # Keep raw Kbps sums -- see format_bandwidth_value() for display
        # formatting (avoids precision loss on sub-1-Mbps values).
        bandwidth_map = {}
        for site_name, sums in site_sums.items():
            bandwidth_map[site_name] = (sums['avg'], sums['peak'])

        debug(f"get_tunnel_bandwidth_map tenant={tenant_tsg_id} built map for {len(bandwidth_map)} sites from {len(data)} tunnel rows")
        return bandwidth_map
    except Exception as e:
        print(f"[!] Error retrieving tunnel bandwidth list for tenant {tenant_tsg_id}: {e}")
        return {}


def extract_tunnel_rows(rn):
    """Given a remote network record, yield (tunnel_name, spn_ip) pairs --
    one per tunnel. Handles both single-tunnel and ECMP (multi-tunnel)
    remote networks."""
    details = rn.get('details') or {}
    spn_ip = details.get('service_ip_address') or details.get('recommended_service_ip_address') or "N/A"

    ecmp_tunnels = rn.get('ecmp_tunnels')
    if ecmp_tunnels:
        for tunnel in ecmp_tunnels:
            tunnel_name = tunnel.get('ipsec_tunnel') or tunnel.get('name') or "Unknown"
            yield tunnel_name, spn_ip
    else:
        tunnel_name = rn.get('ipsec_tunnel') or "Unknown"
        yield tunnel_name, spn_ip


def main():
    global verbose_enabled
    parser = argparse.ArgumentParser(description="Export Remote Networks, tunnels, and SPN name/IP for all child tenants.")
    parser.add_argument('--verbose', action='store_true', help='Print detailed debug output')
    args = parser.parse_args()
    verbose_enabled = args.verbose

    token = get_token()
    if not token:
        sys.exit(1)

    tenants = get_tenants(token)
    print(f"[*] Discovered {len(tenants)} child tenants")

    output_file = "prisma_sase_inventory.csv"
    total_rn_count = 0
    total_row_count = 0
    failed_tenants = []

    with open(output_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Tenant Name', 'Tenant ID', 'Remote Network Name', 'SPN Name', 'Region', 'IPSec Tunnel', 'SPN IP Address', '30-Day Avg Bandwidth', '30-Day Peak Bandwidth'])

        for tenant in tenants:
            t_id = tenant.get('id') or tenant.get('tsg_id') or tenant.get('sub_tenant_id')
            t_name = tenant.get('display_name') or tenant.get('name') or tenant.get('sub_tenant_name', 'Unknown')

            if not t_id or t_id == TSG_ID:
                continue  # Skip the root itself

            try:
                rns = get_remote_networks(t_id)
            except Exception as e:
                print(f"[!] Unexpected error processing tenant {t_name} ({t_id}): {e}")
                failed_tenants.append((t_id, t_name, str(e)))
                continue

            if not rns:
                continue

            # Mint one tenant-scoped token and make ONE tunnel_list call
            # covering every tunnel in this tenant, then look up each
            # remote network's bandwidth from the resulting site_name map.
            bandwidth_token = get_token(scope_tsg_id=t_id)
            bandwidth_map = {}
            if bandwidth_token:
                bandwidth_map = get_tunnel_bandwidth_map(bandwidth_token, t_id)

            total_rn_count += len(rns)
            for rn in rns:
                rn_name = rn.get('name', 'Unknown')
                spn_name = rn.get('spn_name', 'Unknown')
                region = rn.get('region', 'Unknown')

                avg_kbps, peak_kbps = bandwidth_map.get(rn_name, (None, None))
                avg_display = format_bandwidth_value(avg_kbps)
                peak_display = format_bandwidth_value(peak_kbps)

                for tunnel_name, spn_ip in extract_tunnel_rows(rn):
                    writer.writerow([t_name, t_id, rn_name, spn_name, region, tunnel_name, spn_ip, avg_display, peak_display])
                    total_row_count += 1

            print(f"[*] {t_name} ({t_id}): {len(rns)} remote networks")

    print(f"[+] Task Complete. {total_rn_count} remote networks ({total_row_count} tunnel rows) across {len(tenants)} tenants written to {output_file}")
    if failed_tenants:
        print(f"[!] {len(failed_tenants)} tenant(s) failed and were skipped:")
        for t_id, t_name, err in failed_tenants:
            print(f"    - {t_name} ({t_id}): {err}")


if __name__ == "__main__":
    main()
