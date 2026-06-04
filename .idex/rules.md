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
| `LicenseUtilization.license_units` | Units allocated | License utilization API |
| `LicenseUtilization.license_units_used` | Units consumed | License utilization API |
| `LicenseQuota.tsg_id` | TSG Id | License quota API |
| `LicenseQuota.sub_tenant_id` | CDL Tenant Id | License quota API |
| `LicenseQuota.licenseDetails` | Map of `{MU, RN, CDL}` → details | License quota API |

### Correct endpoints for this project

| Purpose | Method | URL |
|---------|--------|-----|
| Auth | POST | `https://auth.apps.paloaltonetworks.com/oauth2/access_token` |
| Tenant hierarchy (with CDL IDs) | GET | `https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/tenant/hierarchy` |
| License utilization (30d) | GET | `https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/license/utilization?agg_by=tenant&product_type=MU,RN&time_period=30d` |
| License quota (assigned) | GET | `https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/license/quota?agg_by=tenant` |
| TSG hierarchy (TSG IDs only) | GET | `https://api.sase.paloaltonetworks.com/tenancy/v1/tenant_service_groups?hierarchy=true` |

> **Note:** The tenancy API (`/tenancy/v1/tenant_service_groups`) returns TSG IDs only.
> The monitor API (`/mt/monitor/v1/agg/custom/tenant/hierarchy`) returns **both** TSG IDs
> and CDL Tenant IDs. Always use the monitor hierarchy endpoint when joining with license data.
