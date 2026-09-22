# Deploying `cert-expiry-report` to IIS

This guide walks through publishing the Certificate Expiry Report Flask
app to Internet Information Services (IIS) on Windows Server using
[`wfastcgi`](https://pypi.org/project/wfastcgi/), Microsoft's supported
bridge for running Python WSGI applications under IIS's FastCGI module.

If you just want to run the app locally for testing, see the
"Local development" section in [`README.md`](README.md) instead — you
do not need IIS for that.

## Prerequisites

- **Windows Server** with **IIS** installed, including the **CGI**
  role service:
  - Server Manager → *Add Roles and Features* → *Web Server (IIS)* →
    *Web Server* → *Application Development* → check **CGI**.
- A **64-bit Python 3.9+** installation on the server (e.g.
  `C:\Python311\python.exe`), accessible to the account IIS runs as.
- Administrator access to the server (elevated PowerShell/cmd) to run
  `wfastcgi-enable` and configure IIS.
- Network/firewall access from the server to
  `https://auth.apps.paloaltonetworks.com` and the Prisma SASE/Strata
  Cloud Manager API endpoints used by the app.

## Step 1 — Copy the project to the server

Copy the entire `cert-expiry-report` folder to the server, for example:

```
C:\inetpub\cert-expiry-report
```

Do **not** copy any `.venv`/`venv` folder from your dev machine — you
will create a fresh virtual environment directly on the server in the
next step (Python virtual environments are not portable across
machines).

## Step 2 — Create a virtual environment and install dependencies

From an elevated PowerShell or cmd prompt on the server:

```powershell
cd C:\inetpub\cert-expiry-report
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

This installs Flask, requests, openpyxl, and `wfastcgi` into the
virtual environment.

## Step 3 — Register wfastcgi with IIS

Still in the activated virtual environment:

```powershell
wfastcgi-enable
```

This command registers a FastCGI application in the IIS configuration
and prints a line similar to:

```
C:\inetpub\cert-expiry-report\.venv\Scripts\python.exe|C:\inetpub\cert-expiry-report\.venv\Lib\site-packages\wfastcgi.py
```

**Copy this exact output** — the two paths (`python.exe` and
`wfastcgi.py`) are needed for the next step.

> If `wfastcgi-enable` fails with a permissions error, make sure the
> prompt is running as Administrator.

## Step 4 — Configure `web.config`

Open [`web.config`](web.config) in the project folder and replace the
three placeholders:

| Placeholder | Replace with |
|---|---|
| `scriptProcessor="C:\path\to\python.exe\|C:\path\to\wfastcgi.py"` | The exact `python.exe\|wfastcgi.py` string printed by `wfastcgi-enable` in Step 3 |
| `<add key="PYTHONPATH" value="C:\path\to\cert-expiry-report" />` | The full deployment path of this folder, e.g. `C:\inetpub\cert-expiry-report` |

Optionally also uncomment and set a stable secret key so Flask's
session secret doesn't rotate every time the application pool
recycles:

```xml
<add key="CERT_REPORT_SECRET_KEY" value="replace-with-a-random-value" />
```

You can generate a random value in PowerShell with:

```powershell
[System.Guid]::NewGuid().ToString()
```

## Step 5 — Create the IIS Application Pool

In **IIS Manager**:

1. Right-click **Application Pools** → **Add Application Pool**.
2. Name it (e.g. `CertExpiryReportPool`).
3. Set **.NET CLR version** to **No Managed Code** (this is a pure
   Python/FastCGI app; the .NET runtime is not used).
4. Leave the **Managed pipeline mode** at its default.
5. After creation, open the pool's **Advanced Settings** and confirm
   the **Identity** has read access to the deployment folder (see
   Step 7).

## Step 6 — Create the IIS Site or Application

In **IIS Manager**:

1. Right-click **Sites** (or an existing site, if adding this as a
   sub-application) → **Add Website** (or **Add Application**).
2. **Site name / Alias**: e.g. `CertExpiryReport`.
3. **Application pool**: select the pool created in Step 5.
4. **Physical path**: point to the deployment folder, e.g.
   `C:\inetpub\cert-expiry-report`.
5. **Binding**: choose a port (e.g. `8080`) or hostname per your
   internal DNS/reverse-proxy setup. HTTPS is strongly recommended
   since Client ID/Secret are submitted via this site — see
   "HTTPS" below.
6. Click **OK**.

## Step 7 — Verify file permissions

The Application Pool identity (by default
`IIS AppPool\CertExpiryReportPool`) needs:

- **Read & execute** access to the entire `cert-expiry-report` folder,
  including `.venv\Lib\site-packages`.
- No write access is required — the app does not write any files to
  disk (reports are streamed directly to the browser as a download).

Grant access via *File Explorer → Properties → Security → Edit → Add*,
entering `IIS AppPool\<YourPoolName>` as the user.

## Step 8 — Browse to the site

Navigate to the site's URL (e.g. `http://your-server:8080/`). You
should see the Certificate Expiry Report form with **Client ID** and
**Client Secret** fields. Submitting valid credentials should trigger
report generation and an automatic `.xlsx` download.

## HTTPS (strongly recommended)

Because this form accepts a Prisma SASE Client ID and Client Secret,
the site should be served over **HTTPS** in any environment beyond a
local loopback test:

1. Bind an SSL certificate to the site in IIS Manager (**Bindings** →
   **Add** → type **https**, select a certificate).
2. Optionally add an HTTP → HTTPS redirect using IIS's **URL Rewrite**
   module.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| **500.19 / 500.0 error immediately on load** | `scriptProcessor`, `WSGI_HANDLER`, or `PYTHONPATH` in `web.config` don't exactly match the paths from `wfastcgi-enable` and your deployment folder. Re-check Step 3/4 for typos. |
| **403.x errors** | The CGI role service isn't installed, or the app pool identity lacks read/execute permission on the folder (Step 7). |
| **Blank page / generic FastCGI error** | Enable `WSGI_LOG` to capture Python tracebacks to a file: add `<add key="WSGI_LOG" value="C:\inetpub\cert-expiry-report\logs\wfastcgi.log" />` to the `<appSettings>` section of `web.config`, ensure the `logs` folder exists and is writable by the app pool identity, then reproduce the error and inspect the log file. |
| **"ModuleNotFoundError: No module named 'app'"** | `PYTHONPATH` in `web.config` doesn't point at the folder containing `wsgi.py`/`app/`. Double-check the value matches the exact deployment path. |
| **Report generation fails for specific tenants only** | This is expected/handled behavior — per-tenant auth or API failures are logged and that tenant is skipped, while the rest of the report still generates. Check `WSGI_LOG` (or IIS's stdout/stderr capture) for `Skipping tenant ... due to error` messages to identify which tenant(s) failed and why (e.g. the provided credentials lack delegated access to that tenant). |
| **Report generation is slow for large hierarchies** | Processing is already concurrent (`MAX_WORKER_THREADS` in `app/config.py`, default 10). If needed, increase this value, but be mindful of API rate limits on the Prisma SASE token/certificate endpoints. |
| **Changes to code aren't reflected after redeploying** | Recycle the Application Pool (IIS Manager → Application Pools → select pool → **Recycle**) so the FastCGI worker process picks up the new files. |

## Updating an existing deployment

To deploy a newer version of the app:

1. Stop the site (or just recycle the app pool) to release file locks.
2. Copy the updated files over the existing deployment folder
   (excluding `.venv`, which does not need to change unless
   `requirements.txt` changed).
3. If `requirements.txt` changed, activate the venv and run
   `pip install -r requirements.txt` again.
4. Recycle the Application Pool in IIS Manager.
5. Re-test by browsing to the site and generating a report.

## Security notes

- Client ID and Client Secret are read from the POST body of each
  request and used only in-memory for that request's duration — they
  are never written to disk, logged, or cached.
- Flask's interactive debugger is explicitly disabled (`debug=False`)
  in both `run.py` and the IIS/wfastcgi entry point (`wsgi.py`), since
  it can execute arbitrary code from a browser session if left
  enabled.
- Request body size is capped both in Flask (`MAX_CONTENT_LENGTH` in
  `app/__init__.py`) and in IIS (`requestFiltering` in `web.config`),
  since this app only ever expects a small credentials form
  submission.
- Serve the site over HTTPS (see above) so credentials are not sent
  in plaintext over the network.
