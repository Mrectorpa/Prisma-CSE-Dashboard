"""
WSGI entry point used by wfastcgi when hosting this app under IIS.

web.config points its FastCGI handler at:
    WSGI_HANDLER = wsgi.app

wfastcgi imports this module and calls the WSGI-callable `app` object
for every request - it does not use `run.py` (that file is for local
development only, since it starts Flask's own dev server).
"""
from app import create_app

app = create_app()
