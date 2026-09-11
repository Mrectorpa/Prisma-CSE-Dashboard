"""
app.py
------
Local Flask web frontend for the Prisma SASE report scripts:
  - prisma_license_report.py         (RN + MU license utilization -> .xlsx)
  - prisma_cert_expiration_report.py (expiring/expired certificates -> .html)

Run locally with:
    python app.py

Then open http://localhost:5000 in a browser.

Design notes:
  - Credentials (Client ID / Client Secret / Root TSG ID) are submitted
    via an HTML form over the local Flask session and are held ONLY in
    server-process memory for the duration of a single report-generation
    job. They are never written to disk, logged, or persisted anywhere.
  - Each report runs in a background thread so the browser isn't blocked
    on a single long HTTP request. The frontend polls a small JSON status
    endpoint to render a live progress bar (tenant N of M).
  - This app is intended for local/single-user use only (no auth, no
    multi-tenant job isolation, in-memory job store). It is NOT designed
    to be exposed on a shared network or the public internet.
"""

import os
import threading
import traceback
import uuid
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, abort

import prisma_license_report
import prisma_cert_expiration_report

# Force a deterministic working directory regardless of how/where the
# process is launched from (e.g. IIS's httpPlatformHandler launches the
# interpreter with a working directory controlled by web.config). Both
# report scripts write output files using relative paths, and the
# /download route serves files relative to os.getcwd(), so pinning the
# cwd to this file's own directory keeps that behavior correct in any
# hosting environment (local dev, IIS, etc.).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------
# Keyed by job_id (uuid4 string). Each job dict tracks status/progress for
# a single report-generation run. This is intentionally simple (no DB, no
# persistence) since the app is meant for local single-user use.
#
# Job dict shape:
#   {
#     "type":        "license" | "cert",
#     "status":      "running" | "done" | "error",
#     "current":     int,   # tenants processed so far
#     "total":       int,   # total tenants to process (0 until known)
#     "stage":       str,   # human-readable current stage label
#     "result_file": str | None,   # output file path, once done
#     "log_file":    str | None,   # companion .log file (cert report only)
#     "error":       str | None,   # error message, if status == "error"
#     "started_at":  str,
# }
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Both report scripts store credentials in MODULE-LEVEL globals
# (CLIENT_ID/CLIENT_SECRET/TSG_ID), not per-call state. Running two jobs
# concurrently would let one job's credentials clobber the other's
# mid-run. A single process-wide lock keeps report generation
# serialized and correct rather than requiring a larger refactor to
# make the scripts thread-safe.
_run_lock = threading.Lock()


def _new_job(job_type: str) -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "type": job_type,
            "status": "running",
            "current": 0,
            "total": 0,
            "stage": "Starting...",
            "result_file": None,
            "log_file": None,
            "error": None,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    return job_id


def _update_job(job_id: str, **kwargs) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


# ---------------------------------------------------------------------------
# Background job runners
# ---------------------------------------------------------------------------
def _run_license_job(job_id: str, client_id: str, client_secret: str, tsg_id: str) -> None:
    def progress_callback(idx: int, total: int, tenant_name: str) -> None:
        _update_job(
            job_id,
            current=idx,
            total=total,
            stage=f"Fetching license subscription status: {tenant_name} ({idx}/{total})",
        )

    try:
        with _run_lock:
            _update_job(job_id, stage="Authenticating and fetching tenant hierarchy...")
            output_file = prisma_license_report.run_report(
                client_id, client_secret, tsg_id, progress_callback=progress_callback
            )
        _update_job(job_id, status="done", stage="Complete", result_file=output_file)
    except Exception as e:
        traceback.print_exc()
        _update_job(job_id, status="error", error=str(e))


def _run_cert_job(job_id: str, client_id: str, client_secret: str, tsg_id: str) -> None:
    def progress_callback(idx: int, total: int, tenant_name: str) -> None:
        _update_job(
            job_id,
            current=idx,
            total=total,
            stage=f"Checking certificates: {tenant_name} ({idx}/{total})",
        )

    try:
        with _run_lock:
            _update_job(job_id, stage="Authenticating and fetching tenant hierarchy...")
            output_file, log_file = prisma_cert_expiration_report.run_report(
                client_id, client_secret, tsg_id, progress_callback=progress_callback
            )
        _update_job(
            job_id, status="done", stage="Complete",
            result_file=output_file, log_file=log_file,
        )
    except Exception as e:
        traceback.print_exc()
        _update_job(job_id, status="error", error=str(e))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    """Landing page: choose which report to generate."""
    return render_template("index.html")


@app.route("/report/<report_type>", methods=["GET", "POST"])
def report_form(report_type: str):
    """Credential entry form for the selected report type."""
    if report_type not in ("license", "cert"):
        abort(404)

    if request.method == "POST":
        client_id     = request.form.get("client_id", "").strip()
        client_secret = request.form.get("client_secret", "").strip()
        tsg_id        = request.form.get("tsg_id", "").strip()

        if not client_id or not client_secret or not tsg_id:
            return render_template(
                "report_form.html",
                report_type=report_type,
                error="All three fields are required.",
            )

        job_id = _new_job(report_type)
        target = _run_license_job if report_type == "license" else _run_cert_job
        thread = threading.Thread(
            target=target,
            args=(job_id, client_id, client_secret, tsg_id),
            daemon=True,
        )
        thread.start()

        return redirect(url_for("progress_page", job_id=job_id))

    return render_template("report_form.html", report_type=report_type, error=None)


@app.route("/progress/<job_id>")
def progress_page(job_id: str):
    """Live progress page — polls /api/status/<job_id> via JS."""
    job = _get_job(job_id)
    if job is None:
        abort(404)
    return render_template("progress.html", job_id=job_id, report_type=job["type"])


@app.route("/api/status/<job_id>")
def api_status(job_id: str):
    """JSON status endpoint polled by the progress page."""
    job = _get_job(job_id)
    if job is None:
        return jsonify({"error": "unknown job_id"}), 404
    return jsonify(job)


@app.route("/download/<path:filename>")
def download(filename: str):
    """
    Serves a generated report file for download/viewing from the
    current working directory (where the report scripts write output).
    Restricted to the exact filenames produced by the two report
    scripts to avoid exposing arbitrary files on disk.
    """
    safe_name = os.path.basename(filename)
    if not (
        safe_name.startswith("prisma_tenant_license_report_")
        or safe_name.startswith("prisma_cert_expiration_report_")
    ):
        abort(403)
    if not os.path.isfile(safe_name):
        abort(404)
    return send_from_directory(os.getcwd(), safe_name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
