"""
prisma_license_report.py
------------------------
Retrieves MU & RN license assigned/consumed for every child tenant
under a root TSG from the Palo Alto Networks SASE APIs and writes the
results to an Excel workbook (.xlsx) with two sheets — one for RN and
one for MU.

APIs used (pan.dev):
  Auth:
    POST https://auth.apps.paloaltonetworks.com/oauth2/access_token

  Tenant hierarchy  (TenantHierarchy schema — provides id (TSG Id) +
  display_name; used to resolve each child tenant's human-readable name):
    GET  https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/tenant/hierarchy

  License subscription status  (SubscriptionStatus schema — MU, RN, SC, PAB):
    GET  https://api.apps.paloaltonetworks.com/mt/monitoring/v2/license/subscription-status
         Header: X-PANW-Region: <region>
    Note: Calling this endpoint with a token scoped to the ROOT TSG_ID
          returns an AGGREGATED response covering every child tenant
          under that root — each entry in instances.mobile_users[] /
          instances.remote_networks[] carries its OWN "tsg_id" field
          identifying which child tenant that specific entry's
          license_total/license_utilized belongs to. The root TSG_ID
          itself is NOT the tenant the data is about — each entry must
          be joined against the tenant hierarchy using its own tsg_id
          to get the correct tenant name. Because the data's home
          region isn't exposed anywhere else, each region in
          ALL_REGIONS is tried (with retry/backoff on 5xx) until one
          returns non-empty instance data.
    Response shape:
      {
        "data": {
          "instances": {
            "mobile_users":      [{end_date, license_total, license_utilized, tsg_id}],
            "remote_networks":   [{end_date, license_total, license_utilized, tsg_id}],
            "service_connections": [...],
            "pab": [...]
          },
          "total_entries": N
        },
        "requestId": "..."
      }

Key schema facts (OpenAPI spec):
  TenantHierarchy.id           = TSG Id
  TenantHierarchy.display_name = human-readable name
  SubscriptionStatus entry.tsg_id             = TSG Id of the CHILD tenant
                                                 that entry's data belongs to
                                                 (join key into the hierarchy —
                                                 NOT necessarily the root TSG_ID
                                                 used to obtain the token)
  SubscriptionStatus instances.mobile_users[]  = MU license entries
  SubscriptionStatus instances.remote_networks[] = RN license entries
  SubscriptionStatus entry.license_total    = units allocated to that tenant
  SubscriptionStatus entry.license_utilized = units consumed by that tenant
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
AUTH_URL                = "https://auth.apps.paloaltonetworks.com/oauth2/access_token"
SASE_BASE_URL           = "https://api.sase.paloaltonetworks.com"
APPS_BASE_URL           = "https://api.apps.paloaltonetworks.com"
HIERARCHY_URL           = f"{SASE_BASE_URL}/mt/monitor/v1/agg/custom/tenant/hierarchy"
SUBSCRIPTION_STATUS_URL = f"{APPS_BASE_URL}/mt/monitoring/v2/license/subscription-status"


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
# STEP 2 — Fetch tenant hierarchy (child tenant id -> display_name)
# ---------------------------------------------------------------------------
def fetch_tenant_hierarchy(token: str) -> dict[str, str]:
    """
    Calls /mt/monitor/v1/agg/custom/tenant/hierarchy and walks the
    nested TenantHierarchy tree (root + all descendants at any depth),
    building a dict keyed by TSG Id ("id" field):

      name_map : tsg_id -> display_name

    This is used to resolve the human-readable name of whichever child
    tenant a given subscription-status entry's own "tsg_id" refers to.
    """
    print("[2/3] Fetching tenant hierarchy...")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        resp = requests.get(HIERARCHY_URL, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"  HTTP {e.response.status_code}: {e.response.text}")
        return {}
    except requests.exceptions.RequestException as e:
        print(f"  Network error: {e}")
        return {}

    body = resp.json()
    if isinstance(body, list):
        roots = body
    elif "items" in body:
        roots = body["items"]
    elif "data" in body:
        roots = body["data"]
    elif "id" in body:
        roots = [body]
    else:
        roots = []

    name_map: dict[str, str] = {}

    def _walk(node: dict) -> None:
        tsg_id    = str(node.get("id", ""))
        node_name = node.get("display_name", f"Unknown (TSG:{tsg_id})")
        if tsg_id:
            name_map[tsg_id] = node_name
        for child in node.get("children", []):
            _walk(child)

    for root in roots:
        _walk(root)

    print(f"  Resolved {len(name_map)} tenant node(s).")
    return name_map


# ---------------------------------------------------------------------------
# STEP 3 — Fetch license subscription status (aggregated across children)
# ---------------------------------------------------------------------------

# Keys under which each product type's entries are reported in the
# SubscriptionStatus response's "instances" map.
SUBSCRIPTION_INSTANCE_KEYS = {
    "MU": "mobile_users",
    "RN": "remote_networks",
}

# Retry/backoff settings for transient 5xx errors from the API.
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


def fetch_subscription_status(token: str) -> list[dict]:
    """
    Calls /mt/monitoring/v2/license/subscription-status using the
    root-TSG-scoped token, trying each region in ALL_REGIONS (with
    retry/backoff on 5xx) and COLLECTING results from every region that
    returns data (rather than stopping at the first hit), since
    different child tenants may live in different regions.

    Returns a flat list of raw entries, each tagged with:
      _product_type : "MU" or "RN"
      _region       : the region the entry was returned from

    Each entry retains its original fields, including its own "tsg_id"
    identifying the child tenant it belongs to.
    """
    print("[3/3] Fetching MU & RN license subscription status across all regions...")
    headers_base = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    all_entries: list[dict] = []
    seen: set[tuple] = set()

    for region in ALL_REGIONS:
        headers = {**headers_base, "X-PANW-Region": region}
        try:
            resp = _get_with_backoff(SUBSCRIPTION_STATUS_URL, headers, {}, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # 400/404 is expected for regions where this tenant has no data.
            detail = e.response.text.strip() if e.response is not None else ""
            print(f"    [{region}] HTTP {e.response.status_code} — skipping.")
            if detail:
                print(f"      -> {detail[:300]}")
            continue
        except requests.exceptions.RequestException as e:
            print(f"    [{region}] Network error: {e} — skipping.")
            continue

        body = resp.json()
        instances = (body.get("data") or {}).get("instances") or {}

        new_count = 0
        for product_type, instance_key in SUBSCRIPTION_INSTANCE_KEYS.items():
            for entry in instances.get(instance_key, []) or []:
                dedup_key = (str(entry.get("tsg_id", "")), product_type)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                entry = dict(entry)
                entry["_product_type"] = product_type
                entry["_region"] = region
                all_entries.append(entry)
                new_count += 1

        if new_count:
            print(f"    [{region}] +{new_count} new record(s)  (total so far: {len(all_entries)})")

    print(f"  Total unique records across all regions: {len(all_entries)}")
    return all_entries


def build_license_records(entries: list[dict]) -> list[dict]:
    """
    Normalizes raw subscription-status entries (each already tagged with
    _product_type / _region, and carrying its own child-tenant "tsg_id")
    into a flat list of records shaped like:
      {tsg_id, product_type, license_units, license_units_used,
       utilization_percentage, _region}
    """
    records: list[dict] = []
    for entry in entries:
        total_units    = float(entry.get("license_total", 0) or 0)
        utilized_units = float(entry.get("license_utilized", 0) or 0)
        if total_units == 0:
            continue
        util_pct = round(utilized_units / total_units * 100, 1)
        records.append({
            "tsg_id":                 str(entry.get("tsg_id", "")),
            "product_type":           entry.get("_product_type", ""),
            "license_units":          total_units,
            "license_units_used":     utilized_units,
            "utilization_percentage": util_pct,
            "_region":                entry.get("_region", ""),
        })
    return records


# ---------------------------------------------------------------------------
# STEP 4 — Write Excel workbook
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

# MU sheet: license-unit columns
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
    records:    list[dict],
    name_map:   dict[str, str],
    output_file: str,
) -> None:
    """
    Joins subscription-status records with the tenant hierarchy name_map
    (keyed by each record's OWN tsg_id — the child tenant the data
    belongs to, not the root TSG used to authenticate) and writes an
    Excel workbook with two sheets: 'RN' and 'MU'.

    RN sheet: bandwidth values are in Mbps as returned by the API
      (license_total / license_utilized), converted to Mbps/Gbps display.

    MU sheet: license unit counts, taken directly from the
      subscription-status API's license_total / license_utilized values
      for the mobile_users instance.
    """
    print(f"Writing report to '{output_file}'...")

    rn_rows: list[list] = []
    mu_rows: list[list] = []

    for rec in records:
        tsg_id       = rec.get("tsg_id", "")
        product_type = rec.get("product_type", "N/A")
        region       = rec.get("_region", "")
        tenant_name  = name_map.get(tsg_id, f"Unknown (TSG:{tsg_id})")

        raw_util = rec.get("utilization_percentage")
        util_pct = round(float(raw_util), 1) if raw_util is not None else ""

        if product_type == "RN":
            assigned_mbps = float(rec.get("license_units", 0) or 0)
            if assigned_mbps == 0:
                continue
            consumed_mbps = float(rec.get("license_units_used", 0) or 0)

            rn_rows.append([
                tenant_name,
                tsg_id,
                region,
                _fmt_bandwidth(assigned_mbps),
                _fmt_bandwidth(consumed_mbps),
                util_pct,
            ])

        elif product_type == "MU":
            assigned_mu = float(rec.get("license_units", 0) or 0)
            if assigned_mu == 0:
                continue
            consumed_mu = float(rec.get("license_units_used", 0) or 0)
            mu_rows.append([
                tenant_name,
                tsg_id,
                region,
                int(assigned_mu),
                int(consumed_mu),
                util_pct,
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
    (auth -> tenant hierarchy -> subscription status -> xlsx write) and
    returns the path to the generated .xlsx file.

    The report includes a row per child tenant that has MU or RN
    license data — each entry's own "tsg_id" (from the subscription-
    status API response) is joined against the tenant hierarchy to
    resolve that child tenant's display name, so the "Tenant Name" and
    "TSG ID" columns reflect the child tenant the license data actually
    belongs to (not the root TSG used to authenticate).

    If provided, progress_callback(idx, total, tenant_name) is invoked
    once per resolved record (used by callers such as a web frontend
    background job to report live progress).

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

    name_map = fetch_tenant_hierarchy(token)

    entries = fetch_subscription_status(token)
    if not entries:
        raise RuntimeError("No license subscription-status data found in any region.")

    records = build_license_records(entries)
    if not records:
        raise RuntimeError("No MU/RN license records with assigned units found.")

    total = len(records)
    for idx, rec in enumerate(records, start=1):
        tenant_name = name_map.get(rec.get("tsg_id", ""), f"Unknown (TSG:{rec.get('tsg_id', '')})")
        if progress_callback is not None:
            progress_callback(idx, total, tenant_name)

    datestamp   = datetime.date.today().strftime("%Y-%m-%d")
    output_file = f"prisma_tenant_license_report_{datestamp}.xlsx"

    write_xlsx(records, name_map, output_file)
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
