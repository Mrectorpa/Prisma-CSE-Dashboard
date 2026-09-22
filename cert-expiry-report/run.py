"""
Local development entry point.

Usage:
    python run.py

Runs the Flask app with the built-in dev server on http://127.0.0.1:5000.
Not used in the IIS deployment (see wsgi.py / web.config for that path).
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=False by default: this app handles Client ID/Secret input,
    # so the interactive debugger (which can execute arbitrary code from
    # a browser) must never be enabled, even locally.
    app.run(host="127.0.0.1", port=5000, debug=False)
