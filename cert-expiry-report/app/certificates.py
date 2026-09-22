"""
Certificate retrieval for a single tenant.

Pulls the "Mobile Users" folder certificates for a tenant (scoped by the
tenant's own bearer token) and normalizes the `not_valid_after` field
into a Python `datetime` plus a computed `days_until_expiry`.

Certificate expiry dates come back from the API in OpenSSL's default
text format, e.g.:
    "Jan 15 12:00:00 2038 GMT"
    "Sep  1 15:07:25 2035 GMT"   (note the double space for single-digit days)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from .config import CERTIFICATE_FOLDER, CERTIFICATES_URL, HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# OpenSSL's default certificate date format, as seen in not_valid_after /
# not_valid_before fields, e.g. "Jan 15 12:00:00 2038 GMT".
_OPENSSL_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"


class CertificateFetchError(Exception):
    """Raised when the certificates API cannot be reached or parsed."""


@dataclass
class Certificate:
    """A single certificate record, normalized for report generation."""
    name: str
    common_name: str
    subject: str
    issuer: str
    not_valid_after_raw: str
    not_valid_after: Optional[datetime]
    days_until_expiry: Optional[int]
    is_ca: bool
    folder: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)


def _parse_not_valid_after(raw_value: str) -> Optional[datetime]:
    """
    Parse an OpenSSL-style expiry date string into a timezone-aware
    datetime (UTC). Returns None if parsing fails (the certificate will
    still be reported, but without an expiry classification).
    """
    if not raw_value:
        return None

    # Collapse repeated whitespace (OpenSSL uses double-space for
    # single-digit day-of-month, e.g. "Sep  1 15:07:25 2015 GMT") so
    # strptime's %d can match reliably.
    normalized = " ".join(raw_value.split())

    try:
        parsed = datetime.strptime(normalized, _OPENSSL_DATE_FORMAT)
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("Could not parse certificate expiry date: %r", raw_value)
        return None


def get_mobile_users_certificates(access_token: str, tenant_id: str) -> List[Certificate]:
    """
    Fetch all certificates in the "Mobile Users" folder for a tenant.

    Args:
        access_token: Bearer token scoped to the tenant.
        tenant_id: Tenant id, used only for error messages/logging.

    Returns:
        A list of normalized Certificate records (unfiltered by expiry
        window - classification happens in classifier.py).

    Raises:
        CertificateFetchError: on any network, auth, or parsing failure.
    """
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    params = {"folder": CERTIFICATE_FOLDER}

    try:
        response = requests.get(
            CERTIFICATES_URL, headers=headers, params=params, timeout=HTTP_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        raise CertificateFetchError(
            f"Network error fetching certificates for tenant {tenant_id}: {exc}"
        ) from exc

    if response.status_code != 200:
        raise CertificateFetchError(
            f"Certificate request for tenant {tenant_id} failed with HTTP "
            f"{response.status_code}: {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise CertificateFetchError(
            f"Certificate response for tenant {tenant_id} was not valid JSON: {exc}"
        ) from exc

    raw_certs: List[Dict[str, Any]] = payload.get("data", []) or []

    certificates: List[Certificate] = []
    for raw in raw_certs:
        not_valid_after_raw = raw.get("not_valid_after", "") or ""
        not_valid_after = _parse_not_valid_after(not_valid_after_raw)

        days_until_expiry: Optional[int] = None
        if not_valid_after is not None:
            now = datetime.now(timezone.utc)
            days_until_expiry = (not_valid_after.date() - now.date()).days

        certificates.append(
            Certificate(
                name=raw.get("name", "") or "",
                common_name=raw.get("common_name", "") or "",
                subject=raw.get("subject", "") or "",
                issuer=raw.get("issuer", "") or "",
                not_valid_after_raw=not_valid_after_raw,
                not_valid_after=not_valid_after,
                days_until_expiry=days_until_expiry,
                is_ca=bool(raw.get("ca", False)),
                folder=raw.get("folder", "") or CERTIFICATE_FOLDER,
                raw=raw,
            )
        )

    logger.debug(
        "Fetched %d certificate(s) from '%s' folder for tenant %s",
        len(certificates), CERTIFICATE_FOLDER, tenant_id,
    )
    return certificates
