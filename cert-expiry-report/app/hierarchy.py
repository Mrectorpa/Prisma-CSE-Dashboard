"""
Tenant hierarchy discovery.

Fetches the full tenant tree rooted at the fixed parent TSG
(config.PARENT_TSG_ID) and flattens it into a simple list of tenants
so the rest of the pipeline doesn't need to know about the nested
`children` structure returned by the API.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

import requests

from .config import HIERARCHY_URL, HTTP_TIMEOUT_SECONDS, PARENT_TSG_ID

logger = logging.getLogger(__name__)


class HierarchyError(Exception):
    """Raised when the tenant hierarchy cannot be fetched or parsed."""


@dataclass(frozen=True)
class Tenant:
    """A single node in the tenant hierarchy, flattened for easy iteration."""
    id: str
    display_name: str
    parent_id: str


def _flatten(node: Dict[str, Any], out: List[Tenant]) -> None:
    """Recursively walk a hierarchy node and its children, appending Tenants."""
    tenant_id = node.get("id")
    display_name = node.get("display_name") or tenant_id or "Unknown"
    parent_id = node.get("parent_id") or ""

    if tenant_id:
        out.append(Tenant(id=str(tenant_id), display_name=str(display_name), parent_id=str(parent_id)))
    else:
        logger.warning("Encountered hierarchy node with no 'id' field; skipping node itself "
                        "(children, if any, will still be processed): %s", display_name)

    children: List[Dict[str, Any]] = node.get("children") or []
    for child in children:
        _flatten(child, out)


def get_all_tenants(client_id: str, client_secret: str) -> List[Tenant]:
    """
    Fetch the tenant hierarchy rooted at PARENT_TSG_ID and return a flat
    list of every tenant in the tree (including the parent itself).

    A single token scoped to the parent TSG is used for this call, since
    the hierarchy endpoint is expected to return the parent's full
    descendant tree in one response.

    Raises:
        HierarchyError: on any network, auth, or parsing failure.
    """
    # Local import avoids a circular import between auth.py and hierarchy.py
    from .auth import TokenError, get_access_token

    try:
        token = get_access_token(client_id, client_secret, PARENT_TSG_ID)
    except TokenError as exc:
        raise HierarchyError(f"Could not obtain token for parent TSG {PARENT_TSG_ID}: {exc}") from exc

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        response = requests.get(HIERARCHY_URL, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise HierarchyError(f"Network error fetching tenant hierarchy: {exc}") from exc

    if response.status_code != 200:
        raise HierarchyError(
            f"Tenant hierarchy request failed with HTTP {response.status_code}: {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HierarchyError(f"Tenant hierarchy response was not valid JSON: {exc}") from exc

    roots = payload.get("data", [])
    if not roots:
        raise HierarchyError("Tenant hierarchy response contained no 'data' entries.")

    tenants: List[Tenant] = []
    for root in roots:
        _flatten(root, tenants)

    # De-duplicate by id, preserving first-seen order, in case the API
    # ever returns overlapping subtrees.
    seen: set = set()  # tracks tenant ids already added to unique_tenants
    unique_tenants: List[Tenant] = []
    for tenant in tenants:
        if tenant.id not in seen:
            seen.add(tenant.id)
            unique_tenants.append(tenant)

    logger.info("Discovered %d tenants under parent TSG %s", len(unique_tenants), PARENT_TSG_ID)
    return unique_tenants
