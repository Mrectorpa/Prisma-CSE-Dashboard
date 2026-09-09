# Spec: Prisma SASE Certificate Expiration Report

## Objective
Build a new standalone Python script, `prisma_cert_expiration_report.py`, that:
1. Authenticates against the Prisma SASE API (same OAuth2 client_credentials flow as `prisma_license_report.py`).
2. Walks the full tenant hierarchy to discover every child tenant (TSG ID + display name), reusing the same recursive-walk logic as `fetch_tenant_hierarchy()`.
3. For each child tenant, calls `GET /sse/config/v1/certificates?folder=Mobile Users` using the **root-scoped token** with a `Prisma-Tenant: <child_tsg_id>` header per tenant (confirmed — no per-child-tenant OAuth token needed, unlike the MU Insights call).
4. Collects every certificate returned, computes days-until-expiry from today, and classifies each as:
   - **Expired** (expiry date < today) → bold red
   - **Expiring soon** (30–90 days until expiry, inclusive) → bold orange
   - Otherwise → not included in the report (action-items-only — confirmed)
5. Outputs a single self-contained HTML file with a styled table (Tenant Name, TSG ID, Certificate Name, Expiry Date, Days Until Expiry, Status) containing ONLY expired + expiring-soon certificates, that opens directly in a browser via double-click — no server required.

**User**: Internal CSE/support engineer auditing expiring MU certificates across all child tenants of a root TSG.
**Success looks like**: Running `python prisma_cert_expiration_report.py`, entering credentials, and getting an HTML file listing every expired (red/bold) and soon-to-expire (orange/bold, 30–90 days out) certificate across all child tenants — an actionable to-do list, not a full inventory.

## Confirmed Decisions
- Auth: root-scoped token for the certificates call; tenant is selected via a `Prisma-Tenant: <child_tsg_id>` request header per call (not a per-child OAuth token).
- Folder scope: query only `folder=Mobile Users` (matches the provided example exactly) — not looping over multiple folders.
- Output: single self-contained `.html` file (inline `<style>`, no external JS/CSS dependencies) — opens directly in any browser.
- Report content: **action-items only** — certificates that are neither expired nor within the 30–90 day window are omitted entirely from the output.
- Code organization: fully standalone script, duplicating the auth / hierarchy-walk / backoff helper functions from `prisma_license_report.py` rather than importing a shared module (matches existing single-file-per-script precedent).

## Tech Stack
- Python 3.10+ (matches existing script's use of `str | None` union syntax)
- `requests` for HTTP
- `getpass` for credential prompt
- `datetime` for expiry-date math
- Standard library `html` module for escaping; output written via plain string templating (no new dependency needed — avoids adding e.g. Jinja2)

## Commands
- Run: `python prisma_cert_expiration_report.py`
- No build step; no test runner currently configured in this repo (matches existing script's lack of a test suite)

## Project Structure
- New file at repo root: `prisma_cert_expiration_report.py` (sibling to `prisma_license_report.py`, same style/conventions)
- Output file: `prisma_cert_expiration_report_<YYYY-MM-DD>.html` written to repo root (matches the dated-filename convention of the existing `.xlsx` output)

## Code Style
Match `prisma_license_report.py` conventions exactly:
- Module docstring at top describing purpose + API(s) used + key schema facts
- Section-comment banners (`# --- STEP N — ... ---`)
- Typed function signatures using `list[dict]`, `dict[str, str]`, `X | None` union syntax
- `_prompt_credentials()` + module-level globals (`CLIENT_ID`, `CLIENT_SECRET`, `TSG_ID`), duplicated in this standalone script
- Defensive response parsing: check for `list` body, `"data"` key, `"items"` key, single-object fallback — same pattern as `fetch_tenant_hierarchy()` / `fetch_license_utilization_for_region_and_type()`
- Print-based progress logging with `[n/total]` style prefixes, matching existing script's console UX
- Retry-with-backoff on transient 5xx via a duplicated `_get_with_backoff()` helper

Example (expiry classification, illustrative):
```python
def classify_expiry(expiry_date: datetime.date, today: datetime.date) -> str | None:
    """Returns 'expired', 'expiring_soon', or None (not reportable) based on days until expiry."""
    days_left = (expiry_date - today).days
    if days_left < 0:
        return "expired"
    if 30 <= days_left <= 90:
        return "expiring_soon"
    return None
```

## Testing Strategy
No automated test suite exists in this repo for the sibling script; consistent with that precedent, this script will be manually verified against a live tenant. Pure functions like `classify_expiry()` and the certificate-field parser are written to be unit-testable in isolation (no network calls) as a future follow-up, but no test suite is being added in this initial delivery.

## Boundaries
- **Always**: keep credentials out of source (interactive prompt only); escape all API-derived strings before embedding in HTML (avoid HTML/script injection from tenant or cert names); handle missing/malformed expiry fields gracefully (skip + log, don't crash the whole run); handle per-tenant API failures without aborting the whole run.
- **Ask first**: adding any new third-party dependency (e.g. Jinja2, pandas) — default plan uses only `requests` + stdlib.
- **Never**: commit real credentials, TSG IDs, or sample API responses containing customer data into the repo.

## Success Criteria
- [ ] Script authenticates and walks the full tenant hierarchy exactly like the license report (all child tenants discovered, arbitrary nesting depth).
- [ ] Script queries `/sse/config/v1/certificates?folder=Mobile Users` once per child tenant using the root token + `Prisma-Tenant` header.
- [ ] Every certificate is classified as expired / expiring-soon (30–90 days) / not-reportable based on its expiry date vs. today.
- [ ] Output is a single `.html` file, openable by double-click in a browser, listing ONLY expired and expiring-soon certificates with columns: Tenant Name, TSG ID, Certificate Name, Expiry Date, Days Until Expiry, Status.
- [ ] Expired rows render bold red; expiring-soon (30–90 day) rows render bold orange.
- [ ] Script handles per-tenant API failures (4xx/5xx/network) without aborting the whole run — logs and continues to the next tenant.
- [ ] Script prints a summary count of expired vs. expiring-soon certs found, and confirms if zero action items were found.

## Remaining Implementation Risk (non-blocking)
- **Certificate field names are unconfirmed.** No sample JSON response for `/sse/config/v1/certificates` was available at spec time. The implementation will defensively check common field-name variants for the certificate name (`name`) and expiry date (`expiry_date`, `not_valid_after`, `expiration_date`, `valid_until`), and common date formats (ISO date or full ISO datetime). The script will log any certificate record it cannot parse (with the raw record) so field names can be corrected quickly after a first live run against a real tenant, without needing to redesign the script.
