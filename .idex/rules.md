# Project Rules — Prisma CSE Dashboard

## Rule: Always consult pan.dev GitHub repo for Palo Alto Networks API specs

When any task involves Palo Alto Networks APIs (SASE, Prisma Access, Strata, SCM,
Tenancy, IAM, Monitor, License, etc.), **always fetch the raw OpenAPI spec from the
`PaloAltoNetworks/pan.dev` GitHub repository first** before writing any code or
making assumptions about endpoints, field names, or response schemas.

### Why

- The pan.dev website (`https://pan.dev`) is a JavaScript SPA and returns 404 HTML
  to `curl` / non-browser clients — it cannot be scraped for API details.
- The GitHub repo contains the authoritative raw OpenAPI YAML specs that the website
  renders. These specs are machine-readable and always up to date.

### How to look up an API spec

**Step 1 — Discover available spec files**

```bash
curl -s "https://api.github.com/repos/PaloAltoNetworks/pan.dev/git/trees/master?recursive=1" \
  | python3 -c "
import sys, json
tree = json.load(sys.stdin).get('tree', [])
for item in tree:
    p = item['path']
    if p.startswith('openapi-specs/') and p.endswith(('.yaml', '.yml', '.json')):
        print(p)
"
```

Key spec paths (as of 2026):

| API family | Spec file path |
|------------|---------------|
| SASE Tenancy (TSG hierarchy) | `openapi-specs/sase/tenancy/TenantServiceGroup.yaml` |
| SASE MSP Monitor (license, tenant hierarchy) | `openapi-specs/sase/mt-monitor/paloaltonetworks-MSP_Monitoring.yaml` |
| SASE IAM | `openapi-specs/sase/iam/` |
| SASE Auth | `openapi-specs/sase/auth/AuthService.yaml` |
| SASE Subscription / Licenses | `openapi-specs/sase/subscription/Licenses.yaml` |
| SCM Tenancy | `openapi-specs/scm/tenancy/TenantServiceGroup.yaml` |
| Prisma Access Config | `openapi-specs/access/prisma-access-config/` |

**Step 2 — Fetch the raw spec**

```bash
curl -s "https://raw.githubusercontent.com/PaloAltoNetworks/pan.dev/master/<path-to-spec>.yaml"
```

**Step 3 — Extract the relevant section**

```bash
curl -s "https://raw.githubusercontent.com/PaloAltoNetworks/pan.dev/master/<path>.yaml" \
  | python3 -c "
import sys
content = sys.stdin.read()
idx = content.find('<keyword>')   # e.g. 'license', 'tenant', endpoint path
print(content[max(0, idx-100):idx+2000])
"
```

### Critical schema facts learned from this project

| Field | Meaning | Used in |
|-------|---------|---------|
| `TenantHierarchy.id` | TSG Id | Tenancy API |
| `TenantHierarchy.cdlTenantId` | CDL Tenant Id | **Matches `sub_tenant_id` in all license APIs** |
| `TenantHierarchy.display_name` | Human-readable name | Hierarchy endpoint |
| `LicenseUtilization.sub_tenant_id` | CDL Tenant Id (join key) | License utilization API |
| `LicenseUtilization.license_units` | Units allocated (Mbps for RN, count for MU) | License utilization API |
| `LicenseUtilization.license_units_used` | Units consumed — Kbps for RN; **always 0 for MU** | License utilization API |
| `LicenseQuota.tsg_id` | TSG Id | License quota API |
| `LicenseQuota.sub_tenant_id` | CDL Tenant Id | License quota API |
| `LicenseQuota.licenseDetails` | Map of `{MU, RN, CDL}` → details | License quota API |
| `connected_entity_count.data[0].user_count` | Active MU users (30-day window) | Insights 3.0 API |

### Correct endpoints for this project

| Purpose | Method | URL |
|---------|--------|-----|
| Auth | POST | `https://auth.apps.paloaltonetworks.com/oauth2/access_token` |
| Tenant hierarchy (with CDL IDs) | GET | `https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/tenant/hierarchy` |
| License utilization (30d) | GET | `https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/license/utilization?agg_by=tenant&product_type=MU,RN&time_period=30d` |
| License quota (assigned) | GET | `https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/license/quota?agg_by=tenant` |
| MU connected user count (30d) | POST | `https://api.sase.paloaltonetworks.com/insights/v3.0/resource/query/users/agent/connected_entity_count` |
| TSG hierarchy (TSG IDs only) | GET | `https://api.sase.paloaltonetworks.com/tenancy/v1/tenant_service_groups?hierarchy=true` |

> **Note:** The tenancy API (`/tenancy/v1/tenant_service_groups`) returns TSG IDs only.
> The monitor API (`/mt/monitor/v1/agg/custom/tenant/hierarchy`) returns **both** TSG IDs
> and CDL Tenant IDs. Always use the monitor hierarchy endpoint when joining with license data.

---

## Lessons Learned

### 1. Two distinct tenant identifier systems — never conflate them

Palo Alto Networks SASE uses **two separate ID namespaces**:

| Identifier | Field name in hierarchy | Field name in license APIs | Description |
|------------|------------------------|---------------------------|-------------|
| **TSG Id** | `TenantHierarchy.id` | `tsg_id` | Tenant Service Group identifier — used for OAuth2 token scoping, IAM, and tenancy APIs |
| **CDL Tenant Id** | `TenantHierarchy.cdlTenantId` | `sub_tenant_id` | Cloud Data Lake identifier — used as the join key in all license/monitor APIs |

**Root cause of "Unknown" tenant names:** Old scripts keyed name lookups by TSG Id, but license APIs return CDL Tenant Id. The fix is to use the monitor hierarchy endpoint which returns both, then join on CDL Tenant Id.

### 2. `LicenseUtilization.license_units_used` is always 0 for MU

The license utilization API (`/mt/monitor/v1/agg/custom/license/utilization`) never populates `license_units_used` for `product_type=MU`. Do not use it for MU consumption data.

**Correct approach:** Use the Prisma Access Insights 3.0 API:
```
POST /insights/v3.0/resource/query/users/agent/connected_entity_count
```
Response field: `data[0].user_count`

### 3. Insights 3.0 API requires a child-TSG-scoped token — not the root token

The `connected_entity_count` endpoint returns `user_count=0` with `isResourceDataOverridden=true` when called with a **root-TSG-scoped token**, even if a `Prisma-Tenant` header is provided.

**The token itself must be scoped to the child TSG:**
```python
requests.post(
    AUTH_URL,
    data={"grant_type": "client_credentials", "scope": f"tsg_id:{child_tsg_id}"},
    auth=(CLIENT_ID, CLIENT_SECRET),
)
```
No `Prisma-Tenant` header is needed — the token scope determines the tenant context.

### 4. RN bandwidth unit mismatch between assigned and consumed

The license utilization API returns RN bandwidth in **two different units**:

| Field | Unit | Conversion |
|-------|------|------------|
| `license_units` (assigned) | Mbps | Display as-is (or convert to Gbps if ≥ 1000) |
| `license_units_used` (consumed) | **Kbps** | Divide by 1000 to get Mbps before display |

### 5. Multi-region data collection is required

License utilization data is partitioned by CDL region. A single region call will miss tenants in other regions. Always iterate all 9 regions and deduplicate by `(sub_tenant_id, product_type)`:

```
americas  europe  uk  de  ca  jp  au  sg  in
```

### 6. pan.dev website is not scrapable — use the GitHub repo

`https://pan.dev` is a JavaScript SPA. Direct HTTP requests return 404 HTML. Always fetch raw OpenAPI YAML specs from:
```
https://raw.githubusercontent.com/PaloAltoNetworks/pan.dev/master/openapi-specs/...
```

### 7. Never store credentials in source code

Use `getpass.getpass()` for secrets and `input()` for non-sensitive fields. Prompt at runtime. This prevents accidental credential exposure in version control.
