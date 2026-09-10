"""
prisma_cert_expiration_report.py
---------------------------------
Retrieves certificates from the "Mobile Users" folder of every child
tenant under a Prisma SASE root TSG, identifies certificates that are
already expired or expiring within the next 30-90 days, and writes the
results to a single self-contained HTML report that can be opened
directly in a browser.

APIs used (pan.dev):
  Auth:
    POST https://auth.apps.paloaltonetworks.com/oauth2/access_token

  Tenant hierarchy  (TenantHierarchy schema — provides TSG id + display_name):
    GET  https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/tenant/hierarchy

  Certificates  (per child tenant, "Mobile Users" folder):
    GET  https://api.sase.paloaltonetworks.com/sse/config/v1/certificates?folder=Mobile Users
         Header: Prisma-Tenant: <child_tsg_id>
    Note: A single ROOT-scoped token is used for every call. The target
          child tenant is selected via the "Prisma-Tenant" request header
          (confirmed working — unlike the MU Insights API, this endpoint
          does NOT require a token minted specifically for the child TSG).

Key schema facts:
  TenantHierarchy.id           = TSG Id
  TenantHierarchy.display_name = human-readable name
  Certificate record (confirmed against a live response):
    name field:   "name"
    expiry field: "not_valid_after"  (CONFIRMED — this is the field the
                  live API actually populates with the certificate's
                  expiration date/time; other candidate names are kept
                  as fallbacks only in case other cert types differ)
    Accepted date formats:
      - OpenSSL/X.509 ASN1_TIME (CONFIRMED live format):
        "Sep  1 15:07:25 2035 GMT"  (note the double space before a
        single-digit day, e.g. "Jun 29" vs "Sep  1")
      - Full ISO-8601 datetime (fallback): "2025-01-31T00:00:00Z"
      - Plain ISO date (fallback): "2025-01-31"

Report scope (confirmed with requester):
  - ACTION ITEMS ONLY: certificates that are neither expired nor within
    the 30-90 or 91-365 day windows are omitted entirely.
  - Expired certificates are rendered BOLD RED.
  - Certificates expiring in 30-90 days (inclusive) are rendered BOLD
    YELLOW.
  - Certificates expiring in 91-365 days (inclusive) are rendered BOLD
    GREEN.
  - Each column (Tenant Name, TSG ID, Certificate Name, Expiry Date,
    Days Until Expiry, Status) has a live, case-insensitive substring
    filter input beneath its header. Filters combine with AND across
    columns and update the visible rows instantly via inline JavaScript
    — no server or external JS library required, so the report remains
    a single self-contained file.

Logging:
  Every run also writes a full console transcript (including any
  "WARNING:" lines and raw skipped certificate records) to a companion
  .log file: prisma_cert_expiration_report_<YYYY-MM-DD>.log. This makes
  it possible to diagnose an empty/zero-result HTML report (e.g. a
  certificate schema field-name mismatch or a per-tenant API error)
  without needing to re-run the script with output captured manually.
"""

import sys
import getpass
import datetime
import time
import traceback
import html as html_lib
import requests

# ---------------------------------------------------------------------------
# CONFIGURATION  (static / non-sensitive)
# ---------------------------------------------------------------------------
CERT_FOLDER = "Mobile Users"

# Credentials are collected at runtime — never stored in source.
CLIENT_ID:     str = ""
CLIENT_SECRET: str = ""
TSG_ID:        str = ""

# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------
AUTH_URL      = "https://auth.apps.paloaltonetworks.com/oauth2/access_token"
SASE_BASE_URL = "https://api.sase.paloaltonetworks.com"
HIERARCHY_URL = f"{SASE_BASE_URL}/mt/monitor/v1/agg/custom/tenant/hierarchy"
CERTS_URL     = f"{SASE_BASE_URL}/sse/config/v1/certificates"

# Retry/backoff settings for transient 5xx errors.
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
MAX_RETRIES  = 3       # total attempts = 1 initial + (MAX_RETRIES - 1) retries
BACKOFF_BASE = 2.0     # seconds; doubles each retry (2s, 4s, 8s, ...)

# Expiring-soon window (inclusive), in days from today.
EXPIRING_SOON_MIN_DAYS  = 30
EXPIRING_SOON_MAX_DAYS  = 90
# Expiring-later window: anything beyond the expiring-soon window, up to
# and including this many days out, is flagged as a longer-horizon
# heads-up (bold green) rather than an urgent action item.
EXPIRING_LATER_MAX_DAYS = 365

# Candidate field names. "not_valid_after" is CONFIRMED as the field the
# live API populates with the certificate's expiration date/time, so it
# is checked first. The remaining candidates are kept only as fallbacks
# in case other certificate types/endpoints use a different field name.
CERT_NAME_FIELDS   = ["name"]
CERT_EXPIRY_FIELDS = ["not_valid_after", "expiry_date", "expiration_date", "valid_until"]


# ---------------------------------------------------------------------------
# STEP 1 — Authenticate
# ---------------------------------------------------------------------------
def get_access_token() -> str | None:
    """OAuth2 client_credentials grant scoped to the ROOT TSG_ID."""
    print("[1/4] Authenticating...")
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
# STEP 2 — Fetch tenant hierarchy (discover every child tenant)
# ---------------------------------------------------------------------------
def fetch_tenant_hierarchy(token: str) -> dict[str, str]:
    """
    Calls /mt/monitor/v1/agg/custom/tenant/hierarchy.

    Walks the nested TenantHierarchy tree (root + all descendants at any
    depth) and returns a dict keyed by TSG id:

      tenant_map : tsg_id -> display_name
    """
    print("[2/4] Fetching tenant hierarchy...")
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
    elif "cdlTenantId" in body or "id" in body:
        roots = [body]
    else:
        roots = []

    tenant_map: dict[str, str] = {}

    def _walk(node: dict) -> None:
        tsg_id    = str(node.get("id", ""))
        node_name = node.get("display_name", f"Unknown (TSG:{tsg_id})")
        if tsg_id:
            tenant_map[tsg_id] = node_name
        for child in node.get("children", []):
            _walk(child)

    for root in roots:
        _walk(root)

    print(f"  Resolved {len(tenant_map)} tenant node(s).")
    return tenant_map


# ---------------------------------------------------------------------------
# STEP 3 — Fetch certificates per child tenant
# ---------------------------------------------------------------------------
def _get_with_backoff(url: str, headers: dict, params: dict, timeout: int):
    """
    Performs a GET request, retrying on transient 5xx responses with
    exponential backoff. Returns the final `requests.Response` object
    (which may still carry an error status if all retries were
    exhausted). Non-retryable errors are surfaced via raise_for_status()
    by the caller.
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


def fetch_certificates_for_tenant(token: str, tsg_id: str) -> list[dict]:
    """
    Calls /sse/config/v1/certificates?folder=Mobile Users for a single
    child tenant, using the ROOT token plus a "Prisma-Tenant" header to
    select the target tenant.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
        "Prisma-Tenant": tsg_id,
    }
    params = {"folder": CERT_FOLDER}

    try:
        resp = _get_with_backoff(CERTS_URL, headers, params, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        detail = e.response.text.strip() if e.response is not None else ""
        print(f"    [TSG:{tsg_id}] HTTP {e.response.status_code} — skipping.")
        if detail:
            print(f"      -> {detail[:500]}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"    [TSG:{tsg_id}] Network error: {e} — skipping.")
        return []

    body = resp.json()
    if isinstance(body, list):
        records = body
    elif "data" in body:
        records = body["data"]
    elif "items" in body:
        records = body["items"]
    elif "name" in body:
        records = [body]
    else:
        records = []

    return records


def fetch_all_certificates(
    token: str,
    tenant_map: dict[str, str],
    progress_callback=None,
) -> list[tuple[str, str, dict]]:
    """
    Iterates over every child tenant in tenant_map, fetches its
    certificates, and returns a flat list of (tsg_id, tenant_name, cert_record)
    tuples across all tenants.

    If provided, progress_callback(idx, total, tenant_name) is invoked
    after each tenant is processed — used by callers (e.g. a web
    frontend background job) to report live per-tenant progress without
    needing to parse console output.
    """
    print(f"[3/4] Fetching '{CERT_FOLDER}' certificates for {len(tenant_map)} tenant(s)...")
    results: list[tuple[str, str, dict]] = []

    total = len(tenant_map)
    for idx, (tsg_id, tenant_name) in enumerate(tenant_map.items(), start=1):
        certs = fetch_certificates_for_tenant(token, tsg_id)
        if certs:
            print(f"    [{idx}/{total}] {tenant_name} (TSG:{tsg_id}) — {len(certs)} certificate(s)")
        for cert in certs:
            results.append((tsg_id, tenant_name, cert))
        if progress_callback is not None:
            progress_callback(idx, total, tenant_name)

    print(f"  Total certificates retrieved across all tenants: {len(results)}")
    return results


# ---------------------------------------------------------------------------
# STEP 4 — Classify expiry and build the report
# ---------------------------------------------------------------------------
def _first_present(record: dict, candidates: list[str]) -> str | None:
    """Returns the value of the first candidate key present (and non-empty) in record."""
    for key in candidates:
        val = record.get(key)
        if val:
            return val
    return None


# Formats observed/expected from the certificates API. The live API
# returns OpenSSL/X.509 ASN1_TIME-style strings (e.g.
# "Sep  1 15:07:25 2035 GMT" — note the double space before single-digit
# days), which is the format actually returned by
# /sse/config/v1/certificates. ISO variants are kept as fallbacks in case
# other tenants/cert types report differently.
_DATE_STRPTIME_FORMATS = [
    "%b %d %H:%M:%S %Y %Z",   # "Sep  1 15:07:25 2035 GMT"  (OpenSSL ASN1_TIME)
    "%Y-%m-%d",               # "2025-01-31"
]


def _parse_date(raw_value: str) -> datetime.date | None:
    """
    Parses a certificate expiry date string into a date object. Returns
    None if the value can't be parsed by any known format.

    Handles:
      - OpenSSL/X.509 ASN1_TIME format: "Sep  1 15:07:25 2035 GMT"
        (the format actually returned by /sse/config/v1/certificates)
      - Full ISO-8601 datetime: "2025-01-31T00:00:00Z"
      - Plain ISO date: "2025-01-31"
    """
    raw_value = raw_value.strip()

    # Full ISO datetime (optionally with trailing "Z")
    try:
        cleaned = raw_value.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(cleaned).date()
    except ValueError:
        pass

    # OpenSSL ASN1_TIME / plain ISO date formats
    for fmt in _DATE_STRPTIME_FORMATS:
        try:
            return datetime.datetime.strptime(raw_value, fmt).date()
        except ValueError:
            continue

    return None


def classify_expiry(expiry_date: datetime.date, today: datetime.date) -> str | None:
    """
    Returns "expired", "expiring_soon", "expiring_later", or None (not a
    reportable item) based on days until expiry relative to today.

      expired         : already past due (days_left < 0)
      expiring_soon   : 30-90 days out (inclusive)
      expiring_later  : 91-365 days out (inclusive)
      None            : outside all reportable windows (>365 days out)
    """
    days_left = (expiry_date - today).days
    if days_left < 0:
        return "expired"
    if EXPIRING_SOON_MIN_DAYS <= days_left <= EXPIRING_SOON_MAX_DAYS:
        return "expiring_soon"
    if EXPIRING_SOON_MAX_DAYS < days_left <= EXPIRING_LATER_MAX_DAYS:
        return "expiring_later"
    return None


def build_report_rows(
    cert_entries: list[tuple[str, str, dict]],
    today: datetime.date,
) -> list[dict]:
    """
    Walks every (tsg_id, tenant_name, cert_record) entry, extracts the
    certificate name + expiry date, classifies it, and returns only the
    rows that are "expired", "expiring_soon", or "expiring_later"
    (action items / heads-up items).

    Each returned row dict has:
      tenant_name, tsg_id, cert_name, expiry_date (date), days_left (int),
      status ("expired" | "expiring_soon" | "expiring_later")

    Records whose name or expiry date can't be parsed are logged and
    skipped rather than crashing the run.
    """
    rows: list[dict] = []
    unparsed = 0

    for tsg_id, tenant_name, cert in cert_entries:
        cert_name  = _first_present(cert, CERT_NAME_FIELDS)
        raw_expiry = _first_present(cert, CERT_EXPIRY_FIELDS)

        if not cert_name or not raw_expiry:
            unparsed += 1
            print(f"    WARNING: could not find name/expiry field on cert record "
                  f"(tenant={tenant_name}, TSG:{tsg_id}): {cert}")
            continue

        expiry_date = _parse_date(str(raw_expiry))
        if expiry_date is None:
            unparsed += 1
            print(f"    WARNING: could not parse expiry date '{raw_expiry}' "
                  f"(tenant={tenant_name}, TSG:{tsg_id}, cert={cert_name})")
            continue

        status = classify_expiry(expiry_date, today)
        if status is None:
            continue  # not an action item — omitted per action-items-only scope

        rows.append({
            "tenant_name":  tenant_name,
            "tsg_id":       tsg_id,
            "cert_name":    cert_name,
            "expiry_date":  expiry_date,
            "days_left":    (expiry_date - today).days,
            "status":       status,
        })

    if unparsed:
        print(f"  {unparsed} certificate record(s) skipped due to missing/unparseable fields.")

    # Sort: expired first (most overdue first), then expiring-soon, then
    # expiring-later (soonest expiry first within each group).
    _STATUS_ORDER = {"expired": 0, "expiring_soon": 1, "expiring_later": 2}
    rows.sort(key=lambda r: (_STATUS_ORDER.get(r["status"], 99), r["days_left"]))
    return rows


# ---------------------------------------------------------------------------
# STEP 5 — Write self-contained HTML report
# ---------------------------------------------------------------------------
HTML_TEMPLATE_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Prisma SASE Certificate Expiration Report — {generated_on}</title>
<style>
  body {{
    font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    background: #f4f6f8;
    color: #1f2d3d;
    margin: 2rem;
  }}
  h1 {{
    color: #1F4E79;
    margin-bottom: 0.25rem;
  }}
  .meta {{
    color: #5a6b7b;
    margin-bottom: 1.5rem;
    font-size: 0.9rem;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    background: #ffffff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  }}
  th, td {{
    padding: 0.6rem 0.9rem;
    text-align: left;
    border-bottom: 1px solid #e1e6ea;
  }}
  th {{
    background: #1F4E79;
    color: #ffffff;
    position: sticky;
    top: 0;
  }}
  th.filter-row {{
    background: #ffffff;
    padding: 0.4rem 0.6rem;
    position: sticky;
    top: 2.6rem;
  }}
  th.filter-row input {{
    width: 100%;
    box-sizing: border-box;
    padding: 0.35rem 0.5rem;
    font-size: 0.85rem;
    border: 1px solid #c7ccd1;
    border-radius: 4px;
    color: #1f2d3d;
    background: #ffffff;
  }}
  th.filter-row input:focus {{
    outline: none;
    border-color: #1F4E79;
    box-shadow: 0 0 0 2px rgba(31,78,121,0.15);
  }}
  tr:hover {{
    background: #f0f4f8;
  }}
  tr.filtered-out {{
    display: none;
  }}
  .filter-summary {{
    margin-top: 0.75rem;
    font-size: 0.85rem;
    color: #5a6b7b;
  }}
  .expired {{
    color: #c0392b;
    font-weight: bold;
  }}
  .expiring-soon {{
    color: #b8960b;
    font-weight: bold;
  }}
  .expiring-later {{
    color: #1e7e34;
    font-weight: bold;
  }}
  .empty-state {{
    padding: 2rem;
    text-align: center;
    color: #5a6b7b;
    background: #ffffff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  }}
  .legend {{
    margin-top: 1rem;
    font-size: 0.85rem;
    color: #5a6b7b;
  }}
  .legend span {{
    margin-right: 1.5rem;
  }}
  .dot {{
    display: inline-block;
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 50%;
    margin-right: 0.35rem;
  }}
  .dot-expired {{ background: #c0392b; }}
  .dot-soon    {{ background: #b8960b; }}
  .dot-later   {{ background: #1e7e34; }}
</style>
</head>
<body>
<h1>Prisma SASE Certificate Expiration Report</h1>
<div class="meta">
  Generated on {generated_on} &middot; Folder: "{folder}" &middot;
  {expired_count} expired &middot; {soon_count} expiring in {min_days}-{max_days} days &middot;
  {later_count} expiring in {soon_max_plus_one}-{later_max_days} days
</div>
"""

HTML_TEMPLATE_TAIL = """
<div class="legend">
  <span><span class="dot dot-expired"></span>Expired</span>
  <span><span class="dot dot-soon"></span>Expiring in {min_days}-{max_days} days</span>
  <span><span class="dot dot-later"></span>Expiring in {soon_max_plus_one}-{later_max_days} days</span>
</div>
{filter_script}
</body>
</html>
"""

# Inline JS: live, per-column, case-insensitive substring filtering.
# Only injected when the table (and its filter inputs) actually exist —
# the empty-state message has no table/filter row, so no script is needed.
# All matching happens client-side against the already-rendered HTML;
# no data is fetched or sent anywhere, keeping the report fully
# self-contained and safe to open from disk.
FILTER_SCRIPT = """<script>
function filterCertTable() {
  var table = document.getElementById("certTable");
  if (!table) { return; }
  var inputs = table.querySelectorAll(".filter-row input");
  var filters = [];
  inputs.forEach(function (input) {
    filters[parseInt(input.getAttribute("data-col"), 10)] =
      input.value.trim().toLowerCase();
  });

  var rows = table.querySelectorAll("tbody tr");
  var visibleCount = 0;
  rows.forEach(function (row) {
    var cells = row.querySelectorAll("td");
    var isMatch = true;
    for (var i = 0; i < filters.length; i++) {
      var needle = filters[i];
      if (!needle) { continue; }
      var cellText = cells[i] ? cells[i].textContent.toLowerCase() : "";
      if (cellText.indexOf(needle) === -1) {
        isMatch = false;
        break;
      }
    }
    row.classList.toggle("filtered-out", !isMatch);
    if (isMatch) { visibleCount++; }
  });

  var summary = document.getElementById("certTableFilterSummary");
  if (summary) {
    var total = parseInt(table.getAttribute("data-total-rows"), 10) || rows.length;
    summary.textContent = (visibleCount === total)
      ? "Showing all " + total + " row(s)."
      : "Showing " + visibleCount + " of " + total + " row(s) (filtered).";
  }
}
document.addEventListener("DOMContentLoaded", filterCertTable);
</script>"""


def _status_label(status: str) -> str:
    if status == "expired":
        return "EXPIRED"
    if status == "expiring_soon":
        return "EXPIRING SOON"
    return "EXPIRING LATER"


def _status_css_class(status: str) -> str:
    if status == "expired":
        return "expired"
    if status == "expiring_soon":
        return "expiring-soon"
    return "expiring-later"


def write_html_report(rows: list[dict], output_file: str) -> None:
    """
    Writes a single self-contained HTML file with a table of action-item
    certificates (expired + expiring-soon + expiring-later). Expired rows
    are bold red; expiring-soon (30-90 days) rows are bold yellow;
    expiring-later (91-365 days) rows are bold green. Opens directly in a
    browser with no server required.
    """
    print(f"[4/4] Writing report to '{output_file}'...")

    today = datetime.date.today()
    generated_on = today.strftime("%Y-%m-%d")
    expired_count = sum(1 for r in rows if r["status"] == "expired")
    soon_count    = sum(1 for r in rows if r["status"] == "expiring_soon")
    later_count   = sum(1 for r in rows if r["status"] == "expiring_later")

    head = HTML_TEMPLATE_HEAD.format(
        generated_on=generated_on,
        folder=html_lib.escape(CERT_FOLDER),
        expired_count=expired_count,
        soon_count=soon_count,
        later_count=later_count,
        min_days=EXPIRING_SOON_MIN_DAYS,
        max_days=EXPIRING_SOON_MAX_DAYS,
        soon_max_plus_one=EXPIRING_SOON_MAX_DAYS + 1,
        later_max_days=EXPIRING_LATER_MAX_DAYS,
    )
    tail = HTML_TEMPLATE_TAIL.format(
        min_days=EXPIRING_SOON_MIN_DAYS,
        max_days=EXPIRING_SOON_MAX_DAYS,
        soon_max_plus_one=EXPIRING_SOON_MAX_DAYS + 1,
        later_max_days=EXPIRING_LATER_MAX_DAYS,
        # Only inject the filter <script> when there's a table to filter —
        # the empty-state message has no filter inputs, so no JS is needed.
        filter_script=FILTER_SCRIPT if rows else "",
    )

    if not rows:
        body = '<div class="empty-state">No expired or expiring certificates found. ✅</div>'
    else:
        row_html = []
        for r in rows:
            css_class = _status_css_class(r["status"])
            row_html.append(
                "<tr class=\"{cls}\">"
                "<td class=\"{cls}\">{tenant}</td>"
                "<td class=\"{cls}\">{tsg}</td>"
                "<td class=\"{cls}\">{cert}</td>"
                "<td class=\"{cls}\">{expiry}</td>"
                "<td class=\"{cls}\">{days}</td>"
                "<td class=\"{cls}\">{label}</td>"
                "</tr>".format(
                    cls=css_class,
                    tenant=html_lib.escape(r["tenant_name"]),
                    tsg=html_lib.escape(r["tsg_id"]),
                    cert=html_lib.escape(r["cert_name"]),
                    expiry=r["expiry_date"].strftime("%Y-%m-%d"),
                    days=r["days_left"],
                    label=_status_label(r["status"]),
                )
            )
        total_row_count = len(rows)
        # Per-column live text filter inputs. Each input's data-col attribute
        # matches the 0-based <td> index it filters; filterTable() (in the
        # tail's inline <script>) reads all six inputs and shows only rows
        # whose corresponding cell text contains every non-empty filter
        # value (case-insensitive substring match, AND across columns).
        filter_row = (
            "<tr class=\"filter-row\">"
            + "".join(
                f'<th class="filter-row"><input type="text" data-col="{i}" '
                f'oninput="filterCertTable()" placeholder="Filter..." '
                f'aria-label="Filter {label}"></th>'
                for i, label in enumerate([
                    "Tenant Name", "TSG ID", "Certificate Name",
                    "Expiry Date", "Days Until Expiry", "Status",
                ])
            )
            + "</tr>"
        )
        body = (
            f'<table id="certTable" data-total-rows="{total_row_count}">'
            "<thead>"
            "<tr>"
            "<th>Tenant Name</th><th>TSG ID</th><th>Certificate Name</th>"
            "<th>Expiry Date</th><th>Days Until Expiry</th><th>Status</th>"
            "</tr>"
            f"{filter_row}"
            "</thead>"
            f"<tbody>{''.join(row_html)}</tbody>"
            "</table>"
            '<div class="filter-summary" id="certTableFilterSummary"></div>'
        )

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(head)
        f.write(body)
        f.write(tail)

    print(f"Done — {expired_count} expired, {soon_count} expiring-soon, "
          f"{later_count} expiring-later certificate(s) written to '{output_file}'.")


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
    print("  Prisma SASE Certificate Expiration Report — Credential Setup")
    print("=" * 60)
    CLIENT_ID     = input("  Service Account Client ID : ").strip()
    CLIENT_SECRET = getpass.getpass("  Client Secret             : ")
    TSG_ID        = input("  Root TSG ID               : ").strip()
    if not CLIENT_ID or not CLIENT_SECRET or not TSG_ID:
        print("\nERROR: All three credential fields are required.")
        sys.exit(1)
    print()


class _TeeLogger:
    """
    Duplicates every write() to both the original stream (console) and an
    open log file handle, so the full console transcript — including
    "WARNING:" lines and raw skipped-record dumps — is always captured to
    disk for later diagnosis, without changing any existing print() calls.
    """
    def __init__(self, original_stream, log_file_handle):
        self._original = original_stream
        self._log      = log_file_handle

    def write(self, data: str) -> None:
        self._original.write(data)
        self._log.write(data)

    def flush(self) -> None:
        self._original.flush()
        self._log.flush()


def run_report(
    client_id: str,
    client_secret: str,
    tsg_id: str,
    progress_callback=None,
) -> tuple[str, str]:
    """
    Non-interactive orchestration entry point (used by both the CLI
    main() below and by external callers such as a web frontend).

    Sets the module-level credential globals, runs the full pipeline
    (auth -> hierarchy -> per-tenant certificates -> classify -> HTML
    write), and returns (output_html_path, log_file_path).

    If provided, progress_callback(idx, total, tenant_name) is forwarded
    to fetch_all_certificates() so a caller can report live progress
    (e.g. for a web UI progress bar) without parsing console/log output.

    Raises RuntimeError (with a human-readable message) on any failure
    instead of calling sys.exit(), so callers embedding this in a
    long-running process (e.g. a Flask background job) can catch and
    report the error without killing the whole process. The full
    console transcript (including this error) is still written to the
    companion .log file for diagnosis either way.
    """
    global CLIENT_ID, CLIENT_SECRET, TSG_ID
    CLIENT_ID     = client_id
    CLIENT_SECRET = client_secret
    TSG_ID        = tsg_id

    today       = datetime.date.today()
    datestamp   = today.strftime("%Y-%m-%d")
    log_file    = f"prisma_cert_expiration_report_{datestamp}.log"
    output_file = f"prisma_cert_expiration_report_{datestamp}.html"

    original_stdout = sys.stdout
    with open(log_file, "w", encoding="utf-8") as log_fh:
        sys.stdout = _TeeLogger(original_stdout, log_fh)
        try:
            print(f"Log file: {log_file}")
            token = get_access_token()
            if not token:
                raise RuntimeError("Could not obtain access token. Check credentials and TSG ID.")

            tenant_map = fetch_tenant_hierarchy(token)
            if not tenant_map:
                raise RuntimeError("No tenants found in hierarchy — nothing to check.")

            cert_entries = fetch_all_certificates(token, tenant_map, progress_callback)
            if not cert_entries:
                raise RuntimeError("No certificates returned for any tenant — nothing to write.")

            rows = build_report_rows(cert_entries, today)

            write_html_report(rows, output_file)
            print("\nReport complete.")
            return output_file, log_file
        except RuntimeError as e:
            print(f"\nERROR: {e}")
            raise
        except Exception:
            # Ensure any unexpected crash is fully captured in the log file
            # (not just printed to a console that may have scrolled away).
            print("\nUNHANDLED ERROR:")
            print(traceback.format_exc())
            raise
        finally:
            sys.stdout = original_stdout


def main() -> None:
    _prompt_credentials()
    try:
        run_report(CLIENT_ID, CLIENT_SECRET, TSG_ID)
    except Exception as e:
        print(f"Aborting: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
