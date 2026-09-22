"""
OAuth2 client_credentials token acquisition for Prisma SASE.

Each tenant in the hierarchy requires its own access token, scoped via
`tsg_id:<tenant_id>`, because the certificates API infers tenant context
entirely from the bearer token's scope (there is no tenant query
parameter on the certificates endpoint).

Credentials (client_id / client_secret) are supplied by the caller for
every request and are never written to disk or logged.
"""
import logging

import requests

from .config import AUTH_TOKEN_URL, HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Raised when a token request fails for a given tenant scope."""


def get_access_token(client_id: str, client_secret: str, tenant_id: str) -> str:
    """
    Request a scoped OAuth2 access token for a single tenant.

    Args:
        client_id: Service account Client ID.
        client_secret: Service account Client Secret.
        tenant_id: Tenant (TSG) id to scope the token to.

    Returns:
        The bearer access token string.

    Raises:
        TokenError: If the token endpoint returns a non-200 response,
            the response body is not valid JSON, or no access_token is
            present in the response.
    """
    data = {
        "grant_type": "client_credentials",
        "scope": f"tsg_id:{tenant_id}",
    }

    try:
        response = requests.post(
            AUTH_TOKEN_URL,
            data=data,
            auth=(client_id, client_secret),
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise TokenError(f"Network error requesting token for tenant {tenant_id}: {exc}") from exc

    if response.status_code != 200:
        raise TokenError(
            f"Token request for tenant {tenant_id} failed with HTTP "
            f"{response.status_code}: {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise TokenError(
            f"Token response for tenant {tenant_id} was not valid JSON: {exc}"
        ) from exc

    token = payload.get("access_token")
    if not token:
        raise TokenError(
            f"Token response for tenant {tenant_id} did not contain an access_token field."
        )

    logger.debug("Obtained access token for tenant %s", tenant_id)
    return token
