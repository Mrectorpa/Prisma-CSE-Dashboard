"""
Flask routes for the certificate expiry report tool.

Single-page workflow:
  GET  /            -> render the Client ID / Client Secret form
  POST /generate     -> run the full pipeline synchronously and return
                         either the .xlsx file (as bytes) or a JSON
                         error payload

The form is submitted via JavaScript `fetch()` (see templates/index.html)
rather than a plain HTML form POST. This is required so the page can
reliably detect when report generation has finished (success or
failure) and hide the "generating" spinner - a plain form submission
that results in a file download does not fire any navigation/load
event the browser exposes to JavaScript, so the spinner would spin
forever even after the file had already been saved.

On success, the response is the raw .xlsx bytes with a
Content-Disposition header. On any failure, the response is JSON:
    { "error": "human readable message" }
with a non-200 status code, which the frontend reads and displays
without ever using window.location or a full form POST/reload.

Credentials submitted via the form are used only for the duration of a
single request (passed in-memory to the orchestrator) and are never
logged, cached, or persisted to disk.
"""
import io
import logging
from datetime import datetime

from flask import Blueprint, Response, jsonify, render_template, request

from .hierarchy import HierarchyError
from .orchestrator import run_report_pipeline
from .report import build_workbook

logger = logging.getLogger(__name__)

bp = Blueprint("report", __name__)


@bp.get("/")
def index() -> str:
    """Render the landing page with the Client ID / Client Secret form."""
    return render_template("index.html")


@bp.post("/generate")
def generate():
    """
    Validate the submitted credentials, run the full report pipeline,
    and return either the resulting workbook (as raw bytes, for the
    frontend to save via a Blob download) or a JSON error payload.
    """
    client_id = (request.form.get("client_id") or "").strip()
    client_secret = (request.form.get("client_secret") or "").strip()

    if not client_id or not client_secret:
        return jsonify(error="Both Client ID and Client Secret are required."), 400

    try:
        result = run_report_pipeline(client_id, client_secret)
    except HierarchyError as exc:
        logger.error("Tenant hierarchy fetch failed: %s", exc)
        return jsonify(
            error=(
                "Could not retrieve the tenant hierarchy. Please verify your "
                "Client ID and Client Secret are correct and have access to "
                "the parent tenant, then try again."
            )
        ), 502
    except Exception:  # noqa: BLE001 - never leak internals to the browser
        logger.exception("Unexpected error while generating the certificate report.")
        return jsonify(
            error="An unexpected error occurred while generating the report. Please try again."
        ), 500
    finally:
        # Defensive: drop local references to the credentials as soon as
        # we're done with them, even though Python's GC will reclaim
        # them regardless. No credential data is logged above.
        client_id = ""
        client_secret = ""

    if not result.tenant_reports:
        return jsonify(
            error=(
                "No tenants had certificates expiring within the next 90 days "
                "(or all tenants failed to process). No report was generated."
            )
        ), 200

    workbook_bytes = build_workbook(result)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Certificate_Report_{timestamp}.xlsx"

    return Response(
        io.BytesIO(workbook_bytes).getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
