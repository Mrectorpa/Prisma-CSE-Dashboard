"""
wsgi.py
-------
Production WSGI entry point for the Prisma CSE Reports Flask app.

Flask's built-in dev server (used by `python app.py`) is NOT suitable for
production/IIS hosting. This module simply re-exports the same `app`
object so a production-grade WSGI server can serve it instead.

IIS hosting (see web.config in this directory) launches:

    <python.exe> -m waitress --listen=127.0.0.1:%HTTP_PLATFORM_PORT% wsgi:app

For manual production-style testing outside IIS, run the same server
locally:

    py -3.13 -m waitress --listen=127.0.0.1:8080 wsgi:app

Then browse to http://127.0.0.1:8080

IMPORTANT — single-process requirement:
This app keeps report-generation jobs in an in-memory dict
(see app.py: _jobs / _jobs_lock / _run_lock) and runs each report in a
background thread of the SAME process that received the HTTP request.
It MUST be served by exactly one persistent worker process:
  - waitress (default) already runs as a single process with a thread
    pool, which is compatible.
  - Do NOT run this behind a FastCGI process pool (e.g. wfastcgi) or an
    IIS "Web Garden" (multiple worker processes per app pool) — a job
    created on one worker process would not be visible to a status-poll
    request served by a different worker process.
"""

from app import app  # noqa: F401  (re-exported WSGI callable, used as "wsgi:app")

if __name__ == "__main__":
    # Convenience: `python wsgi.py` runs the same production server
    # locally via waitress instead of Flask's dev server.
    from waitress import serve

    serve(app, host="127.0.0.1", port=8080)
