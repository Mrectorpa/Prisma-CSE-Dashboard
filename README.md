# Prisma CSE Dashboard

A Python script that queries the Palo Alto Networks SASE APIs to generate a Microsoft Excel report of **Mobile User (MU)** and **Remote Network (RN)** license utilization across all tenants and subtenants for the last 30 days.

---

## Output

The script produces a datestamped Excel workbook:

```
prisma_tenant_license_report_YYYY-MM-DD.xlsx
```

| Sheet | Columns |
|-------|---------|
| **RN** | Tenant Name, Tenant ID, Region, Bandwidth Assigned, Bandwidth Consumed, Utilization % |
| **MU** | Tenant Name, Tenant ID, Region, License Units Assigned, License Units Consumed, Utilization % |

- **RN bandwidth** is displayed in Mbps or Gbps (auto-scaled).
- **MU License Units Consumed** = active connected users over the last 30 days (via Prisma Access Insights 3.0).
- Rows with **zero assigned** licenses are excluded from both sheets.
- **Utilization %** is rounded to one decimal place.

---

## Prerequisites

### Python version
Python 3.10 or later (uses `str | None` union syntax).

### Dependencies
Install required packages:

```bash
pip install requests openpyxl
```

### Palo Alto Networks service account
You need a **service account** with access to the root TSG (Tenant Service Group). The account requires:

- `client_credentials` OAuth2 grant type enabled
- Access to the MSP Monitor APIs (`/mt/monitor/v1/agg/custom/...`)
- Access to the Prisma Access Insights 3.0 API (`/insights/v3.0/...`)
- Superuser or equivalent role on the root TSG and all child TSGs

You will need:
| Field | Example |
|-------|---------|
| **Client ID** | `my-svc-account@1234567890.iam.panserviceaccount.com` |
| **Client Secret** | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| **Root TSG ID** | `1234567890` |

---

## Usage

```bash
python prisma_license_report.py
```

The script prompts for credentials at startup — nothing is stored in the source code:

```
============================================================
  Prisma SASE License Report — Credential Setup
============================================================
  Service Account Client ID : my-svc-account@1234567890.iam.panserviceaccount.com
  Client Secret             : (not echoed)
  Root TSG ID               : 1234567890
```

### Expected runtime
- Steps 1–3 (auth, hierarchy, utilization) complete in under 60 seconds.
- The MU user-count step calls the Insights API once per tenant with an assigned MU license. Each call acquires a child-scoped token and queries the API — expect **~30–90 seconds per tenant** depending on API response time.

---

## How It Works

### Authentication
OAuth2 `client_credentials` grant against `https://auth.apps.paloaltonetworks.com/oauth2/access_token`.

For the MU user-count step, a **separate token scoped to each child TSG** is acquired. This is required because the Insights 3.0 API only returns real telemetry when the bearer token is scoped to the specific child TSG — a root-scoped token returns `user_count=0`.

### APIs Used

| Purpose | Method | Endpoint |
|---------|--------|----------|
| Authentication | `POST` | `https://auth.apps.paloaltonetworks.com/oauth2/access_token` |
| Tenant hierarchy | `GET` | `/mt/monitor/v1/agg/custom/tenant/hierarchy` |
| License utilization (MU + RN) | `GET` | `/mt/monitor/v1/agg/custom/license/utilization` |
| MU connected user count | `POST` | `/insights/v3.0/resource/query/users/agent/connected_entity_count` |

All SASE API calls go to `https://api.sase.paloaltonetworks.com`.

### Regions
The script queries all 9 CDL regions and deduplicates results:

```
americas  europe  uk  de  ca  jp  au  sg  in
```

### Key Schema Facts
- `TenantHierarchy.id` = TSG Id
- `TenantHierarchy.cdlTenantId` = CDL Tenant Id (matches `sub_tenant_id` in license APIs)
- `LicenseUtilization.license_units` = assigned (Mbps for RN, count for MU)
- `LicenseUtilization.license_units_used` = consumed Kbps for RN; always `0` for MU (use Insights API instead)

---

## Files

| File | Description |
|------|-------------|
| `prisma_license_report.py` | Main script |
| `prisma_tenant_license_report_YYYY-MM-DD.xlsx` | Generated report (created at runtime) |
| `.idex/rules.md` | Project-level AI assistant rules |

---

## API Reference

API specifications are sourced from the official Palo Alto Networks OpenAPI repository:
[https://github.com/PaloAltoNetworks/pan.dev](https://github.com/PaloAltoNetworks/pan.dev)
