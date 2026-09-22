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
├── README.md
├── DEPLOY_IIS.md           Full IIS/wfastcgi deployment walkthrough
└── .gitignore
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

For full step-by-step IIS/wfastcgi deployment instructions (prerequisites,
`web.config` setup, IIS site/application pool configuration, HTTPS,
troubleshooting, and update procedures), see
[`DEPLOY_IIS.md`](DEPLOY_IIS.md).

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
