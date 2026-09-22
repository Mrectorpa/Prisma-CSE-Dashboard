"""
Orchestration of the full report pipeline.

For every tenant discovered in the hierarchy:
  1. Request a scoped access token.
  2. Fetch "Mobile Users" folder certificates.
  3. Classify certificates into Expired/Red/Yellow/Green buckets.

Tenants are processed concurrently (bounded thread pool) since each
tenant requires its own independent token + API round trip. Any
per-tenant failure (auth failure, API error, network issue) is logged
and that tenant is skipped - it never aborts the overall report.

Tenants with zero certificates in a reportable bucket are excluded
from the final result entirely (per requirements).
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List

from .auth import TokenError, get_access_token
from .certificates import CertificateFetchError, get_mobile_users_certificates
from .classifier import ClassifiedCertificate, classify_certificates
from .config import MAX_WORKER_THREADS
from .hierarchy import Tenant, get_all_tenants

logger = logging.getLogger(__name__)


@dataclass
class TenantReportData:
    """Reportable data for a single tenant: its info plus classified certs."""
    tenant: Tenant
    classified_certificates: List[ClassifiedCertificate]


@dataclass
class OrchestrationResult:
    """Overall pipeline result: successful tenant data plus run statistics."""
    tenant_reports: List[TenantReportData]
    total_tenants_discovered: int
    tenants_with_reportable_certs: int
    tenants_skipped_due_to_error: int
    tenants_skipped_no_certs: int


def _process_tenant(client_id: str, client_secret: str, tenant: Tenant) -> TenantReportData:
    """
    Process a single tenant: obtain a token, fetch certs, classify them.

    Raises TokenError / CertificateFetchError on failure - the caller
    (run_report_pipeline) is responsible for catching these per-tenant
    so one bad tenant does not abort the whole run.
    """
    token = get_access_token(client_id, client_secret, tenant.id)
    raw_certs = get_mobile_users_certificates(token, tenant.id)
    classified = classify_certificates(raw_certs)
    return TenantReportData(tenant=tenant, classified_certificates=classified)


def run_report_pipeline(client_id: str, client_secret: str) -> OrchestrationResult:
    """
    Execute the full pipeline: discover tenants, then concurrently fetch
    and classify certificates for each one.

    Raises:
        HierarchyError: if the tenant hierarchy itself cannot be fetched
            (this is a hard failure - the parent TSG hierarchy must
            succeed for the report to make any sense).
    """
    tenants = get_all_tenants(client_id, client_secret)

    tenant_reports: List[TenantReportData] = []
    skipped_due_to_error = 0
    skipped_no_certs = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS) as executor:
        future_to_tenant = {
            executor.submit(_process_tenant, client_id, client_secret, tenant): tenant
            for tenant in tenants
        }

        for future in as_completed(future_to_tenant):
            tenant = future_to_tenant[future]
            try:
                result = future.result()
            except (TokenError, CertificateFetchError) as exc:
                logger.warning(
                    "Skipping tenant %s (%s) due to error: %s",
                    tenant.id, tenant.display_name, exc,
                )
                skipped_due_to_error += 1
                continue
            except Exception:  # noqa: BLE001 - defensive: never let one tenant kill the run
                logger.exception(
                    "Unexpected error processing tenant %s (%s); skipping.",
                    tenant.id, tenant.display_name,
                )
                skipped_due_to_error += 1
                continue

            if not result.classified_certificates:
                logger.info(
                    "Tenant %s (%s) has no certificates expiring within the reportable "
                    "window; omitting from report.",
                    tenant.id, tenant.display_name,
                )
                skipped_no_certs += 1
                continue

            tenant_reports.append(result)

    # Sort for deterministic, readable workbook tab ordering.
    tenant_reports.sort(key=lambda r: r.tenant.display_name.lower())

    logger.info(
        "Report pipeline complete: %d tenant(s) discovered, %d with reportable certs, "
        "%d skipped due to error, %d skipped (no reportable certs).",
        len(tenants), len(tenant_reports), skipped_due_to_error, skipped_no_certs,
    )

    return OrchestrationResult(
        tenant_reports=tenant_reports,
        total_tenants_discovered=len(tenants),
        tenants_with_reportable_certs=len(tenant_reports),
        tenants_skipped_due_to_error=skipped_due_to_error,
        tenants_skipped_no_certs=skipped_no_certs,
    )
