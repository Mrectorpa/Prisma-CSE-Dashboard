"""Shared constants for the certificate expiry report tool."""

# Fixed parent Tenant Service Group (TSG). Per requirements this never
# changes and is not user-configurable.
PARENT_TSG_ID = "1602436186"

# Prisma SASE / Strata Cloud Manager API base URLs.
AUTH_TOKEN_URL = "https://auth.apps.paloaltonetworks.com/am/oauth2/access_token"
HIERARCHY_URL = "https://api.sase.paloaltonetworks.com/mt/monitor/v1/agg/custom/tenant/hierarchy"
CERTIFICATES_URL = "https://api.sase.paloaltonetworks.com/sse/config/v1/certificates"

# Only the "Mobile Users" folder is in scope for this report.
CERTIFICATE_FOLDER = "Mobile Users"

# Expiry window thresholds (in days from "today").
RED_THRESHOLD_DAYS = 30
YELLOW_THRESHOLD_DAYS = 60
GREEN_THRESHOLD_DAYS = 90

# Status bucket labels used throughout classification and the report.
STATUS_EXPIRED = "Expired"
STATUS_RED = "Red"
STATUS_YELLOW = "Yellow"
STATUS_GREEN = "Green"

# HTTP timeouts (seconds) for outbound calls to the Prisma SASE APIs.
HTTP_TIMEOUT_SECONDS = 30

# Max number of tenants processed concurrently.
MAX_WORKER_THREADS = 10
