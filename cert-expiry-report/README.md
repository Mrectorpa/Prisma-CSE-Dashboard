# Certificate Expiry Report

A small internal web tool that scans the Prisma SASE tenant hierarchy
(parent TSG `1602436186` and every descendant tenant) for **Mobile
Users** folder certificates expiring within the next 90 days, and
produces an Excel workbook with one tab per tenant.

## What it does

1. You enter your Prisma SASE **Client ID** and **Client Secret** in a
   simple web form (these are never stored or logged - they are used
   only for the duration of your request).
2. The app fetches the tenant hierarchy rooted at the fixed parent TSG
   `1602436186` and flattens it into a list of every descendant tenant.
3. For each tenant, the app requests a scoped OAuth2 token
   (`scope=tsg_id:<tenant_id>`) and fetches that tenant's "Mobile
   Users" folder certificates.
4. Each certificate is classified by days-until-expiry:
   - **Expired** - already past its `not_valid_after` date
   - **Red** - expires within 30 days
   - **Yellow** - expires in 31-60 days
   - **Green** - expires in 61-90 days
   - Certificates with more than 90 days of remaining validity are
     excluded from the report.
5. Tenants with zero certificates in a reportable bucket are omitted
   from the workbook entirely.
6. The resulting `.xlsx` (a "Summary" tab plus one tab per tenant with
   reportable certificates) is downloaded immediately in your browser.

## Project layout

```
cert-expiry-report/
├── app/
│   ├── __init__.py        Flask application factory
│   ├── config.py          Shared constants (parent TSG, API URLs, thresholds)
│   ├── auth.py            OAuth2 client_credentials token fetching
│   ├── hierarchy.py       Tenant hierarchy fetch + flattening
│   ├── certificates.py    Per-tenant "Mobile Users" certificate fetch/parse
│   ├── classifier.py      Expiry bucket classification (Expired/Red/Yellow/Green)
│   ├── orchestrator.py    Concurrent multi-tenant pipeline coordination
│   ├── report.py          openpyxl workbook generation
│   ├── routes.py          Flask routes (form + report generation/download)
│   ├── templates/
│   │   └── index.html     Single-page form UI
│   └── static/
│       └── style.css
├── requirements.txt
├── run.py                 Local development entry point (Flask dev server)
├── wsgi.py                Production/IIS entry point (used by wfastcgi)
├── web.config              IIS + wfastcgi configuration
└── README.md
```

## Local development

```bash
cd cert-expiry-report
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python run.py
```

Then open http://127.0.0.1:5000 in a browser and submit your Client ID
and Client Secret.

## Deploying to IIS

This app is deployed to IIS using [`wfastcgi`](https://pypi.org/project/wfastcgi/),
Microsoft's supported bridge for running Python WSGI applications under
IIS's FastCGI module.

### 1. Prerequisites on the IIS server

- Windows Server with IIS installed, including the **CGI** role service
  (Server Manager → Add Roles and Features → Web Server (IIS) → Web
  Server → Application Development → CGI).
- A 64-bit Python 3.9+ install available to the IIS server (e.g.
  `C:\Python311\python.exe`).

### 2. Install dependencies

Copy this `cert-expiry-report` folder to the server (e.g.
`C:\inetpub\cert-expiry-report`), then:

```powershell
cd C:\inetpub\cert-expiry-report
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Register wfastcgi with IIS

From an elevated PowerShell/cmd prompt, with the venv activated:

```powershell
wfastcgi-enable
```

This prints a line similar to:

```
C:\inetpub\cert-expiry-report\.venv\Scripts\python.exe|C:\inetpub\cert-expiry-report\.venv\Lib\site-packages\wfastcgi.py
```

Copy that exact string - you'll need the two paths (`python.exe` and
`wfastcgi.py`) for the next step.

### 4. Update `web.config`

Open `web.config` in this folder and replace the placeholders:

- `scriptProcessor="C:\path\to\python.exe|C:\path\to\wfastcgi.py"` →
  use the exact paths printed by `wfastcgi-enable` in step 3.
- `<add key="PYTHONPATH" value="C:\path\to\cert-expiry-report" />` →
  the full deployment path of this folder (e.g.
  `C:\inetpub\cert-expiry-report`).

Optionally set a stable `CERT_REPORT_SECRET_KEY` value (any random
string) so Flask's secret key doesn't rotate on every app pool
recycle.

### 5. Create the IIS site/application

In IIS Manager:

1. Create a new **Application Pool** (e.g. `CertExpiryReportPool`) with
   **.NET CLR version: No Managed Code**.
2. Create a new **Website** or **Application** pointing its physical
   path at this folder (e.g. `C:\inetpub\cert-expiry-report`), assigned
   to the application pool created above.
3. Ensure the application pool's identity has read access to this
   folder (and, if using a venv, to the venv's `site-packages`).
4. Browse to the site. You should see the Client ID / Client Secret
   form.

### 6. Troubleshooting

- **500.0 errors on load**: check that `WSGI_HANDLER`, the
  `scriptProcessor` paths, and `PYTHONPATH` in `web.config` exactly
  match your Python/venv install paths.
- **Report generation errors**: application logs go to stdout/stderr,
  which IIS's FastCGI module typically writes to the Application Pool's
  configured error log location, or can be captured via
  `stderr` mode diagnostics in `wfastcgi` (`WSGI_LOG` app setting can be
  added to `web.config` to write logs to a file, e.g.
  `<add key="WSGI_LOG" value="C:\inetpub\cert-expiry-report\logs\wfastcgi.log" />`).
- **Auth/token failures for specific tenants**: these are logged and
  the tenant is skipped automatically - the overall report still
  generates using every tenant that succeeded. Check the logs for
  `Skipping tenant ... due to error` messages to identify which
  tenants failed and why (e.g. missing delegated access).

## Security notes

- The Client ID and Client Secret are read from the POST body on each
  request and passed directly, in memory, to the token-fetching code.
  They are never written to disk, added to logs, or cached between
  requests.
- Flask's interactive debugger is explicitly disabled (`debug=False`)
  in both `run.py` and the IIS/wfastcgi path, since it can execute
  arbitrary code from a browser session if left enabled.
- Request body size is capped (both in Flask's `MAX_CONTENT_LENGTH` and
  IIS's `requestFiltering` config) since this app only ever expects a
  small credentials form submission.
