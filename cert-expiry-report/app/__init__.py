"""
Certificate Expiry Report - Flask application factory.

This package implements a small internal web tool that:
  1. Accepts a Prisma SASE (Strata Cloud Manager) Client ID / Client Secret
     from the user via a web form (never stored, never logged).
  2. Walks the tenant hierarchy starting at the fixed parent TSG
     (1602436186), discovering every descendant tenant.
  3. For each tenant, requests a scoped OAuth2 access token and pulls the
     "Mobile Users" folder certificates.
  4. Classifies each certificate by days-until-expiry into
     Expired / Red (<=30d) / Yellow (31-60d) / Green (61-90d) buckets,
     discarding anything with more than 90 days of remaining validity.
  5. Builds an .xlsx workbook (Summary tab + one tab per tenant) and
     returns it to the browser as an immediate file download.
"""
import logging
import os

from flask import Flask


def create_app() -> Flask:
    """Application factory used by both `run.py` (dev) and wfastcgi (IIS)."""
    app = Flask(__name__)

    # Keep logs on stdout/console (and, on IIS, in the FastCGI stderr log)
    # so operators can diagnose per-tenant failures without needing access
    # to any persisted credential data (none is ever written to disk).
    log_level = os.environ.get("CERT_REPORT_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Flask needs a secret key for flashing messages / session use even
    # though this app does not persist any user session data.
    app.config["SECRET_KEY"] = os.environ.get("CERT_REPORT_SECRET_KEY", os.urandom(24))

    # Max request body size (form submission is tiny - this just guards
    # against abuse). 1 MB is generous for a Client ID/Secret form post.
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

    from . import routes  # noqa: WPS433 (local import avoids circular import)
    app.register_blueprint(routes.bp)

    return app
