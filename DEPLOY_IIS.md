# Hosting on Microsoft IIS

This app can be hosted on Windows/IIS using the **httpPlatformHandler**
module, which launches a single persistent Python process (running a
[`waitress`](https://docs.pylonsproject.org/projects/waitress/) WSGI server)
and proxies all HTTP requests to it.

> **Why not FastCGI (`wfastcgi`)?**
> This app keeps report jobs in an in-memory dict and runs each report in a
> background thread of the same worker process that accepted the request
> (see `app.py: _jobs` / `_run_lock`). FastCGI manages a *pool* of worker
> processes, so a progress-poll request could be routed to a different
> process than the one running the job and incorrectly 404. httpPlatformHandler
> instead runs exactly one long-lived process, which matches this app's design.

---

## 1. Prerequisites on the IIS server

- Windows Server with IIS installed.
- **[httpPlatformHandler](https://www.iis.net/downloads/microsoft/httpplatformhandler)**
  module installed (adds the `<httpPlatform>` config section used by `web.config`).
- Python 3.10+ installed on the server (3.13 recommended — matches the
  version used during development/testing of this app).
- Network access from the server to `https://auth.apps.paloaltonetworks.com`
  and `https://api.sase.paloaltonetworks.com` (outbound HTTPS, 443).

---

## 2. Deploy the code

1. Copy the project folder to the server, e.g.
   `C:\inetpub\wwwroot\Prisma-CSE-Dashboard\`.
2. Open an elevated command prompt in that folder and create a virtual
   environment with the dependencies (including `waitress`, the production
   WSGI server used instead of Flask's dev server):
   ```cmd
   cd C:\inetpub\wwwroot\Prisma-CSE-Dashboard
   py -3.13 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
3. Create the log folder IIS will write to (already present as `logs\` with
   a `.gitkeep` placeholder — just confirm it exists):
   ```cmd
   mkdir logs
   ```

---

## 3. Configure `web.config`

Open [`web.config`](web.config:1) and update the `processPath` in the
`<httpPlatform>` element to the **absolute path** of the venv's
`python.exe` on the target server (IIS does not resolve relative paths or
`PATH` lookups for this setting):

```xml
<httpPlatform processPath="C:\inetpub\wwwroot\Prisma-CSE-Dashboard\.venv\Scripts\python.exe"
               arguments="-m waitress --listen=127.0.0.1:%HTTP_PLATFORM_PORT% wsgi:app"
               ...
```

`%HTTP_PLATFORM_PORT%` is a token IIS substitutes automatically at runtime
with a free local port it has reserved for the backend process — leave it
as-is.

---

## 4. Create the IIS site / application

1. In **IIS Manager**, right-click **Sites** → **Add Website** (or add an
   **Application** under an existing site):
   - **Physical path**: `C:\inetpub\wwwroot\Prisma-CSE-Dashboard`
   - **Binding**: choose the host header / port for this app (e.g. `:80` or
     a dedicated hostname; HTTPS via an IIS binding + certificate is
     strongly recommended since credentials are submitted via this app —
     see Security section below).
2. Set the **Application Pool** for this site to:
   - **.NET CLR version**: **No Managed Code**
   - **Identity**: a service account (or `ApplicationPoolIdentity`) that
     has **Modify** permission on the project folder, since the report
     scripts write output files (`.xlsx`, `.html`, `.log`) there at runtime.
   - **Start Mode**: `AlwaysRunning` (optional, avoids cold-start delay on
     the first request after idle).
   - Ensure the app pool does **not** use a "Web Garden" (multiple worker
     processes) — must remain a single process, per the design note above.
3. Grant the app pool identity Modify/Write on the project folder:
   ```cmd
   icacls "C:\inetpub\wwwroot\Prisma-CSE-Dashboard" /grant "IIS AppPool\<YourAppPoolName>:(OI)(CI)M"
   ```

---

## 5. Verify

1. Browse to the site's configured URL. You should see the dashboard
   ("📊 License Report" / "🔐 Certificate Expiration Report" tiles).
2. Submit a report form with valid Prisma SASE credentials and confirm the
   progress page updates and a download link appears when complete.
3. If something goes wrong, check `logs\stdout.log` in the project folder —
   this captures everything the Python process prints to stdout/stderr,
   including Flask/waitress startup messages and any unhandled exceptions
   from the report scripts.

---

## 6. Security notes for a shared/production host

The app was originally designed for local single-user use. Before exposing
it on an internal network via IIS, consider:

- **Use HTTPS** (bind an IIS certificate) since the credential form submits
  a Client Secret over the wire.
- **Restrict network access** (e.g. IIS IP restrictions, internal-only DNS)
  since there is no login/authentication on the app itself — anyone who can
  reach the URL can submit Prisma SASE credentials and trigger a report.
- **Single-user assumption still applies**: the in-memory job store is not
  partitioned per-user, so if hosted for multiple simultaneous users, one
  user could see another's job IDs if guessed (job IDs are random UUIDs,
  which are not practically guessable) and generated report files under
  `/download/` are shared/world-readable to anyone who can reach the site.
  For genuine multi-user isolation, per-user auth and per-job access control
  would need to be added.
- **Report files accumulate on disk** (`prisma_tenant_license_report_*.xlsx`,
  `prisma_cert_expiration_report_*.html/.log`) — set up a scheduled task to
  periodically clean up old files in the project folder if disk usage is a
  concern.

---

## 7. Local production-style testing (without IIS)

To test the exact same production server (waitress) locally before
deploying to IIS:

```cmd
py -3.13 -m pip install -r requirements.txt
py -3.13 wsgi.py
```

Then browse to `http://127.0.0.1:8080`. This uses the same `wsgi:app`
entry point that IIS's `httpPlatformHandler` launches, so a successful run
here is a strong signal the IIS deployment will behave the same way.
