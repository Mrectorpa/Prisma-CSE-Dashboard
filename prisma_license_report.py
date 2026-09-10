"""
prisma_license_report.py
------------------------
Retrieves tenant and subtenant names along with MU & RN license
assigned and consumed (last 30 days) from the Palo Alto Networks
SASE APIs and writes the results to an Excel workbook (.xlsx) with
two sheets — one for RN and one for MU.

APIs used (pan.dev):
  Auth:
    POST https://auth.apps.paloaltonetworks.com/oauth2/access_token

  Tenant hierarchy  (TenantHierarchy schema — provides cdlTenantId + display_name):
    GET  https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/tenant/hierarchy

  License utilization  (LicenseUtilization schema — MU & RN, last 30 days):
    GET  https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/license/utilization
         ?agg_by=tenant&product_type=<MU|RN>&time_period=30d
         Header: X-PANW-Region: <region>
    Note: product_type is queried separately per type (MU, then RN) rather
          than as a combined "MU,RN" value — some regions' backend
          aggregation returns a 5xx "Unexpected server error" when both
          product types are requested together for tenants with real data.
          Requests are also retried with exponential backoff on 5xx errors.

  MU user count  (Insights 3.0 — connected_entity_count):
    POST https://api.sase.paloaltonetworks.com/insights/v3.0/resource/query/users/agent/connected_entity_count
    Note: Must use a token scoped to the CHILD TSG ID (tsg_id:<child_tsg_id>), NOT the root TSG.
          The root-scoped token returns user_count=0 with isResourceDataOverridden=true.
          No Prisma-Tenant header is needed when the token is already child-scoped.

Key schema facts (OpenAPI spec):
  TenantHierarchy.id           = TSG Id
  TenantHierarchy.cdlTenantId  = CDL Tenant Id  ← matches sub_tenant_id in license APIs
  TenantHierarchy.display_name = human-readable name
  LicenseUtilization.sub_tenant_id    = CDL Tenant Id  (join key)
  LicenseUtilization.product_type     = "MU" or "RN"
  LicenseUtilization.license_units    = units allocated to the tenant
  LicenseUtilization.license_units_used = units consumed (always 0 for MU)
  LicenseUtilization.utilization_percentage = consumed / allocated * 100
  Insights connected_entity_count.data[0].user_count = active MU users (30-day window)
"""

import sys
import getpass
import datetime
import time
import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# CONFIGURATION  (static / non-sensitive)
# ---------------------------------------------------------------------------
# All 9 CDL regions supported by the X-PANW-Region header (per OpenAPI spec)
ALL_REGIONS = ["americas", "europe", "uk", "de", "ca", "jp", "au", "sg", "in"]

# Credentials are collected at runtime — never stored in source.
CLIENT_ID:     str = ""
CLIENT_SECRET: str = ""
TSG_ID:        str = ""

# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------
AUTH_URL        = "https://auth.apps.paloaltonetworks.com/oauth2/access_token"
SASE_BASE_URL   = "https://api.sase.paloaltonetworks.com"
HIERARCHY_URL   = f"{SASE_BASE_URL}/mt/monitor/v1/agg/custom/tenant/hierarchy"
UTILIZATION_URL = f"{SASE_BASE_URL}/mt/monitor/v1/agg/custom/license/utilization"
INSIGHTS_MU_URL = f"{SASE_BASE_URL}/insights/v3.0/resource/query/users/agent/connected_entity_count"


# ---------------------------------------------------------------------------
# STEP 1 — Authenticate
# ---------------------------------------------------------------------------
def get_access_token() -> str | None:
    """OAuth2 client_credentials grant scoped to TSG_ID."""
    print("[1/3] Authenticating...")
    try:
        resp = requests.post(
            AUTH_URL,
            data={"grant_type": "client_credentials", "scope": f"tsg_id:{TSG_ID}"},
            auth=(CLIENT_ID, CLIENT_SECRET),
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            print(f"  ERROR: access_token missing. Response: {resp.text}")
            return None
        print("  OK")
        return token
    except requests.exceptions.HTTPError as e:
        print(f"  HTTP {e.response.status_code}: {e.response.text}")
    except requests.exceptions.RequestException as e:
        print(f"  Network error: {e}")
    return None


# ---------------------------------------------------------------------------
# STEP 2 — Fetch tenant hierarchy
# ---------------------------------------------------------------------------
def fetch_tenant_hierarchy(token: str) -> tuple[dict, dict]:
    """
    Calls /mt/monitor/v1/agg/custom/tenant/hierarchy.

    Walks the nested TenantHierarchy tree and builds two dicts
    keyed by cdlTenantId (which matches sub_tenant_id in license APIs):

      name_map   : cdlTenantId -> display_name
      parent_map : cdlTenantId -> parent display_name  (absent for root nodes)
    """
    print("[2/3] Fetching tenant hierarchy...")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        resp = requests.get(HIERARCHY_URL, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"  HTTP {e.response.status_code}: {e.response.text}")
        return {}, {}
    except requests.exceptions.RequestException as e:
        print(f"  Network error: {e}")
        return {}, {}

    body = resp.json()
    if isinstance(body, list):
        roots = body
    elif "items" in body:
        roots = body["items"]
    elif "data" in body:
        roots = body["data"]
    elif "cdlTenantId" in body or "id" in body:
        roots = [body]
    else:
        roots = []

    name_map:   dict[str, str] = {}
    parent_map: dict[str, str] = {}
    tsg_map:    dict[str, str] = {}   # cdlTenantId -> TSG id

    def _walk(node: dict, parent_name: str | None) -> None:
        cdl_id    = str(node.get("cdlTenantId", ""))
        tsg_id    = str(node.get("id", ""))
        node_name = node.get("display_name", f"Unknown (TSG:{tsg_id})")
        if cdl_id:
            name_map[cdl_id]  = node_name
            tsg_map[cdl_id]   = tsg_id
            if parent_name is not None:
                parent_map[cdl_id] = parent_name
        for child in node.get("children", []):
            _walk(child, node_name)

    for root in roots:
        _walk(root, None)

    print(f"  Resolved {len(name_map)} tenant node(s).")
    return name_map, parent_map, tsg_map


# ---------------------------------------------------------------------------
# STEP 3 — Fetch license utilization (assigned + consumed, last 30 days)
# ---------------------------------------------------------------------------

# Product types are queried individually (rather than as a combined
# "MU,RN" param) because some regions' backend aggregation fails with a
# 5xx "Unexpected server error" when both product types are requested
# together for tenants that actually have data. Splitting the calls lets
# one product type succeed even if the other keeps failing.
PRODUCT_TYPES = ["MU", "RN"]

# Retry/backoff settings for transient 5xx errors from the Insights Service.
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
MAX_RETRIES  = 3       # total attempts = 1 initial + (MAX_RETRIES - 1) retries
BACKOFF_BASE = 2.0     # seconds; doubles each retry (2s, 4s, 8s, ...)


def _get_with_backoff(url: str, headers: dict, params: dict, timeout: int):
    """
    Performs a GET request, retrying on transient 5xx responses with
    exponential backoff. Returns the final `requests.Response` object
    (which may still carry an error status if all retries were
    exhausted). Non-retryable errors (4xx, network errors) are raised
    immediately/propagated on the first attempt via raise_for_status()
    or the underlying exception.
    """
    attempt = 1
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        if resp.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
            wait = BACKOFF_BASE * (2 ** (attempt - 1))
            print(f"      (HTTP {resp.status_code} — retrying in {wait:.0f}s, "
                  f"attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)
            attempt += 1
            continue
        return resp


def fetch_license_utilization_for_region_and_type(
    token: str, region: str, product_type: str
) -> list[dict]:
    """
    Calls /mt/monitor/v1/agg/custom/license/utilization for a single
    region AND a single product type ("MU" or "RN"), retrying transient
    5xx failures with backoff before giving up.

    Each LicenseUtilization record contains:
      sub_tenant_id       : CDL Tenant Id  (join key to hierarchy)
      product_type        : "MU" or "RN"
      license_units       : units allocated to the tenant
      license_units_used  : units consumed in the 30-day window
      utilization_percentage
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-PANW-Region": region,
    }
    params = {
        "agg_by":       "tenant",
        "product_type": product_type,
        "time_period":  "30d",
    }

    try:
        resp = _get_with_backoff(UTILIZATION_URL, headers, params, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # 400/404 is expected for regions where this tenant has no data.
        # 5xx means the API itself failed after exhausting retries — surface
        # the response body so the actual cause (bad scope, malformed param,
        # backend error, etc.) is visible.
        detail = e.response.text.strip() if e.response is not None else ""
        print(f"    [{region}/{product_type}] HTTP {e.response.status_code} — skipping.")
        if detail:
            print(f"      -> {detail[:500]}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"    [{region}/{product_type}] Network error: {e} — skipping.")
        return []

    body = resp.json()
    if isinstance(body, list):
        records = body
    elif "items" in body:
        records = body["items"]
    elif "data" in body:
        records = body["data"]
    elif "sub_tenant_id" in body:
        records = [body]
    else:
        records = []

    # Tag each record with its source region
    for rec in records:
        rec["_region"] = region
    return records


def fetch_license_utilization_for_region(token: str, region: str) -> list[dict]:
    """
    Calls /mt/monitor/v1/agg/custom/license/utilization for a single
    region, once per product type (MU, RN), and combines the results.
    """
    recs: list[dict] = []
    for product_type in PRODUCT_TYPES:
        recs.extend(fetch_license_utilization_for_region_and_type(token, region, product_type))
    return recs


def fetch_license_utilization_all_regions(token: str) -> list[dict]:
    """
    Iterates over ALL_REGIONS, collects utilization records from each,
    and deduplicates by (sub_tenant_id, product_type) — keeping the record
    from the first region that returned data for that tenant/product pair.
    """
    print("[3/3] Fetching MU & RN license utilization across all regions...")
    seen:    set[tuple] = set()
    all_recs: list[dict] = []

    for region in ALL_REGIONS:
        recs = fetch_license_utilization_for_region(token, region)
        new_count = 0
        for rec in recs:
            key = (str(rec.get("sub_tenant_id", "")), rec.get("product_type", ""))
            if key not in seen:
                seen.add(key)
                all_recs.append(rec)
                new_count += 1
        if new_count:
            print(f"    [{region}] +{new_count} new record(s)  (total so far: {len(all_recs)})")

    print(f"  Total unique records across all regions: {len(all_recs)}")
    return all_recs


# ---------------------------------------------------------------------------
# STEP 3c — Fetch MU user_count per tenant via Insights 3.0
# ---------------------------------------------------------------------------
def _get_child_token(child_tsg_id: str) -> str | None:
    """
    Acquires an OAuth2 token scoped to a specific child TSG ID.

    The Insights 3.0 connected_entity_count API returns real data only when
    the bearer token is scoped to the child TSG (tsg_id:<child_tsg_id>).
    A root-scoped token always returns user_count=0 with
    isResourceDataOverridden=true.
    """
    try:
        resp = requests.post(
            AUTH_URL,
            data={"grant_type": "client_credentials", "scope": f"tsg_id:{child_tsg_id}"},
            auth=(CLIENT_ID, CLIENT_SECRET),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception:
        return None


def fetch_mu_counts(
    mu_tenants: list[tuple[str, str, str]],  # list of (cdl_id, tsg_id, region)
    name_map:   dict[str, str],              # cdl_id -> display_name
    progress_callback=None,
) -> dict[str, int]:
    """
    For each MU tenant, acquires a child-TSG-scoped token then calls:
      POST /insights/v3.0/resource/query/users/agent/connected_entity_count

    Key insight: the token MUST be scoped to the child TSG ID, not the root.
    No Prisma-Tenant header is needed — the token scope determines the tenant.

    If provided, progress_callback(idx, total, tenant_name) is invoked
    after each tenant is processed — used by callers (e.g. a web
    frontend background job) to report live per-tenant progress without
    needing to parse console output.

    Returns a dict: cdl_id -> user_count
    """
    print(f"      Fetching MU user counts via Insights API ({len(mu_tenants)} tenant(s) — may be slow)...")
    mu_map: dict[str, int] = {}

    payload = {
        "filter": {
            "rules": [
                {"operator": "last_n_days",  "property": "event_time",     "values": [30]},
                {"operator": "in",           "property": "platform_type",  "values": ["prisma_access"]},
                {"operator": "in",           "property": "connect_method", "values": ["AGENT"]},
            ]
        }
    }

    total = len(mu_tenants)
    for idx, (cdl_id, child_tsg_id, region) in enumerate(mu_tenants, start=1):
        tenant_name = name_map.get(cdl_id, f"Unknown (TSG:{child_tsg_id})")

        # Acquire a token scoped to this specific child TSG
        child_token = _get_child_token(child_tsg_id)
        if not child_token:
            print(f"        [{idx}/{total}] {tenant_name} — token acquisition failed, skipping.")
            mu_map[cdl_id] = 0
            continue

        headers = {
            "Authorization": f"Bearer {child_token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
            "X-PANW-Region": region,
        }
        try:
            resp = requests.post(INSIGHTS_MU_URL, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json().get("data", [{}])
            count = int(data[0].get("user_count", 0)) if data else 0
        except Exception as e:
            print(f"        [{idx}/{total}] {tenant_name} — Insights API error: {e}")
            count = 0

        mu_map[cdl_id] = count
        print(f"        [{idx}/{total}] {tenant_name} (region={region}) → user_count={count}")
        if progress_callback is not None:
            progress_callback(idx, total, tenant_name)

    nonzero = sum(1 for v in mu_map.values() if v > 0)
    print(f"      Done — {nonzero} tenant(s) with user_count > 0.")
    return mu_map


# ---------------------------------------------------------------------------
# STEP 4 — Merge and write Excel workbook
# ---------------------------------------------------------------------------

# RN sheet: bandwidth columns use human-readable Mbps/Gbps labels
RN_COLUMNS = [
    "Tenant Name",
    "TSG ID",
    "Region",
    "Bandwidth Assigned",
    "Bandwidth Consumed",
    "Utilization %",
]

# MU sheet: user-count columns (no unit conversion needed)
MU_COLUMNS = [
    "Tenant Name",
    "TSG ID",
    "Region",
    "MU Licenses Assigned",
    "MU Licenses usage",
    "Utilization %",
]

HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")


def _fmt_bandwidth(value_mbps: float) -> str:
    """
    Convert a Mbps value to a human-readable string.
    Values >= 1000 Mbps are shown as Gbps (1 decimal place).
    Values < 1000 Mbps are shown as Mbps (1 decimal place).
    """
    if value_mbps >= 1000:
        return f"{value_mbps / 1000:.1f} Gbps"
    return f"{value_mbps:.1f} Mbps"


def _write_sheet(ws, columns: list[str], rows: list[list]) -> None:
    """Write header + data rows to a worksheet and auto-size columns."""
    ws.append(columns)
    for cell in ws[1]:
        cell.fill      = HEADER_FILL
        cell.font      = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    for row in rows:
        ws.append(row)

    for col_idx, _ in enumerate(columns, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = max(
            len(str(ws.cell(row=r, column=col_idx).value or ""))
            for r in range(1, ws.max_row + 1)
        )
        ws.column_dimensions[col_letter].width = min(max_len + 4, 60)


def write_xlsx(
    util_records: list[dict],
    name_map:     dict[str, str],
    parent_map:   dict[str, str],
    tsg_map:      dict[str, str],
    mu_map:       dict[str, int],
    output_file:  str,
) -> None:
    """
    Joins utilization records with hierarchy names and writes an Excel
    workbook with two sheets: 'RN' and 'MU'.

    RN sheet: bandwidth values converted from raw API units to Mbps/Gbps.
      - license_units      is in Mbps  (license_unit field = "Mbps")
      - license_units_used is in Kbps  (license_used_unit field = "Kbps")
        → divide by 1000 to get Mbps, then format as Mbps or Gbps.

    MU sheet: user counts. License Units Consumed = muCount from
      /mt/monitor/v1/agg/custom/license/setup/status (keyed by tsg_id),
      because license_units_used is always 0 for MU in the utilization API.
    """
    print(f"Writing report to '{output_file}'...")

    rn_rows: list[list] = []
    mu_rows: list[list] = []

    for rec in util_records:
        cdl_id       = str(rec.get("sub_tenant_id", ""))
        product_type = rec.get("product_type", "N/A")

        node_name = name_map.get(cdl_id, f"Unknown (CDL:{cdl_id})")
        tsg_id    = tsg_map.get(cdl_id, "")
        region    = rec.get("_region", "")

        raw_util = rec.get("utilization_percentage")
        util_pct = round(float(raw_util), 1) if raw_util is not None else ""

        if product_type == "RN":
            # Assigned: already in Mbps
            assigned_mbps = float(rec.get("license_units", 0) or 0)
            # Skip tenants with no assigned bandwidth
            if assigned_mbps == 0:
                continue
            # Consumed: API returns Kbps → convert to Mbps
            consumed_mbps = float(rec.get("license_units_used", 0) or 0) / 1000

            rn_rows.append([
                node_name,
                tsg_id,
                region,
                _fmt_bandwidth(assigned_mbps),
                _fmt_bandwidth(consumed_mbps),
                util_pct,
            ])

        elif product_type == "MU":
            assigned_mu = float(rec.get("license_units", 0) or 0)
            # Skip tenants with no assigned MU licenses
            if assigned_mu == 0:
                continue
            # user_count from Insights API (keyed by cdl_id)
            consumed_mu = mu_map.get(cdl_id, 0)
            # Compute utilization % from actual values (API always returns 0 for MU)
            mu_util_pct = round(consumed_mu / assigned_mu * 100, 1) if assigned_mu else ""
            mu_rows.append([
                node_name,
                tsg_id,
                region,
                int(assigned_mu),
                consumed_mu,
                mu_util_pct,
            ])

    wb = Workbook()

    # Sheet 1 — RN
    ws_rn = wb.active
    ws_rn.title = "RN"
    _write_sheet(ws_rn, RN_COLUMNS, rn_rows)

    # Sheet 2 — MU
    ws_mu = wb.create_sheet(title="MU")
    _write_sheet(ws_mu, MU_COLUMNS, mu_rows)

    wb.save(output_file)
    print(f"Done — {len(rn_rows)} RN row(s) on 'RN' sheet, "
          f"{len(mu_rows)} MU row(s) on 'MU' sheet → '{output_file}'.")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def _prompt_credentials() -> None:
    """
    Interactively prompts the user for credentials at runtime.
    CLIENT_SECRET is collected with getpass so it is not echoed to the terminal.
    Values are written into the module-level globals used by all API functions.
    """
    global CLIENT_ID, CLIENT_SECRET, TSG_ID
    print("=" * 60)
    print("  Prisma SASE License Report — Credential Setup")
    print("=" * 60)
    CLIENT_ID     = input("  Service Account Client ID : ").strip()
    CLIENT_SECRET = getpass.getpass("  Client Secret             : ")
    TSG_ID        = input("  Root TSG ID               : ").strip()
    if not CLIENT_ID or not CLIENT_SECRET or not TSG_ID:
        print("\nERROR: All three credential fields are required.")
        sys.exit(1)
    print()


def run_report(
    client_id: str,
    client_secret: str,
    tsg_id: str,
    progress_callback=None,
) -> str:
    """
    Non-interactive orchestration entry point (used by both the CLI
    main() below and by external callers such as a web frontend).

    Sets the module-level credential globals, runs the full pipeline
    (auth -> hierarchy -> utilization -> MU counts -> xlsx write), and
    returns the path to the generated .xlsx file.

    If provided, progress_callback(idx, total, tenant_name) is forwarded
    to fetch_mu_counts() (the slowest, per-tenant step) so a caller can
    report live progress (e.g. for a web UI progress bar).

    Raises RuntimeError (with a human-readable message) on any failure
    instead of calling sys.exit(), so callers embedding this in a
    long-running process (e.g. a Flask background job) can catch and
    report the error without killing the whole process.
    """
    global CLIENT_ID, CLIENT_SECRET, TSG_ID
    CLIENT_ID     = client_id
    CLIENT_SECRET = client_secret
    TSG_ID        = tsg_id

    token = get_access_token()
    if not token:
        raise RuntimeError("Could not obtain access token. Check credentials and TSG ID.")

    name_map, parent_map, tsg_map = fetch_tenant_hierarchy(token)
    util_records                  = fetch_license_utilization_all_regions(token)

    if not util_records:
        raise RuntimeError("No utilization records returned — nothing to write.")

    # Build list of (cdl_id, tsg_id, region) for MU tenants that have assigned licenses
    mu_tenants: list[tuple[str, str, str]] = []
    seen_cdl: set[str] = set()
    for rec in util_records:
        if rec.get("product_type") == "MU":
            assigned = float(rec.get("license_units", 0) or 0)
            cdl_id   = str(rec.get("sub_tenant_id", ""))
            region   = rec.get("_region", ALL_REGIONS[0])
            child_tsg_id = tsg_map.get(cdl_id, "")
            if assigned > 0 and cdl_id and cdl_id not in seen_cdl and child_tsg_id:
                seen_cdl.add(cdl_id)
                mu_tenants.append((cdl_id, child_tsg_id, region))

    mu_map = fetch_mu_counts(mu_tenants, name_map, progress_callback)

    datestamp   = datetime.date.today().strftime("%Y-%m-%d")
    output_file = f"prisma_tenant_license_report_{datestamp}.xlsx"

    write_xlsx(util_records, name_map, parent_map, tsg_map, mu_map, output_file)
    print("\nReport complete.")
    return output_file


def main() -> None:
    _prompt_credentials()
    try:
        run_report(CLIENT_ID, CLIENT_SECRET, TSG_ID)
    except RuntimeError as e:
        print(f"Aborting: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
