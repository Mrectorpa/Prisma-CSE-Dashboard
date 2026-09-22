"""
Certificate expiry classification.

Buckets each certificate by days-until-expiry:
    - Expired:  days_until_expiry < 0 (already expired)
    - Red:      0 <= days_until_expiry <= 30
    - Yellow:   31 <= days_until_expiry <= 60
    - Green:    61 <= days_until_expiry <= 90
    - (discarded): days_until_expiry > 90, or unparsable expiry date

Only certificates that fall into one of the four buckets above are kept
in the report; anything with more than 90 days of remaining validity is
dropped, as is any certificate whose expiry date could not be parsed.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

from .certificates import Certificate
from .config import (
    GREEN_THRESHOLD_DAYS,
    RED_THRESHOLD_DAYS,
    STATUS_EXPIRED,
    STATUS_GREEN,
    STATUS_RED,
    STATUS_YELLOW,
    YELLOW_THRESHOLD_DAYS,
)

logger = logging.getLogger(__name__)


@dataclass
class ClassifiedCertificate:
    """A Certificate paired with its computed expiry status bucket."""
    certificate: Certificate
    status: str


def classify_certificate(certificate: Certificate) -> Optional[str]:
    """
    Return the status bucket for a single certificate, or None if the
    certificate should be excluded from the report (expiry unknown or
    more than GREEN_THRESHOLD_DAYS away).
    """
    days = certificate.days_until_expiry
    if days is None:
        return None

    if days < 0:
        return STATUS_EXPIRED
    if days <= RED_THRESHOLD_DAYS:
        return STATUS_RED
    if days <= YELLOW_THRESHOLD_DAYS:
        return STATUS_YELLOW
    if days <= GREEN_THRESHOLD_DAYS:
        return STATUS_GREEN
    return None


def classify_certificates(certificates: List[Certificate]) -> List[ClassifiedCertificate]:
    """
    Classify a list of certificates, returning only those that fall
    within the Expired/Red/Yellow/Green windows (>90 day and unparsable
    certs are silently dropped from the result).
    """
    classified: List[ClassifiedCertificate] = []
    for cert in certificates:
        status = classify_certificate(cert)
        if status is not None:
            classified.append(ClassifiedCertificate(certificate=cert, status=status))

    logger.debug(
        "Classified %d of %d certificate(s) into reportable expiry buckets",
        len(classified), len(certificates),
    )
    return classified
