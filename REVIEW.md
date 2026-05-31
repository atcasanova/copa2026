# Security and Bug Review

This review intentionally excludes committed `.env` concerns because this checkout is a test environment. The findings below cover the remaining issues found during inspection.

## High Severity

### Predictable runtime security defaults in code

- Files: `backend/app/auth.py:13`, `backend/app/main.py:65`, `backend/app/main.py:67`, `backend/app/db.py:5`
- Issue: The backend has production-capable fallback values for `JWT_SECRET`, bootstrap admin username/email/password, and `DATABASE_URL`.
- Impact: If an environment variable is missing in any deployment-like environment, the app silently falls back to known credentials/secrets. A known JWT secret allows token forgery.
- Recommendation: Fail startup when required secrets are absent. Do not provide real-looking defaults for auth, admin bootstrap, or database credentials.

### Automatic bootstrap admin with predictable password

- File: `backend/app/main.py:64`
- Issue: On startup, the app creates a `system_admin` user if the configured bootstrap username does not exist.
- Impact: A missing or reset user table can expose an admin account with a predictable password if bootstrap variables are defaulted or reused.
- Recommendation: Require an explicit one-time bootstrap flow, or only create the admin when a strong bootstrap password is supplied and a separate `ENABLE_ADMIN_BOOTSTRAP=true` flag is set.

### Overly permissive CORS configuration

- File: `backend/app/main.py:24`
- Issue: `allow_origins=["*"]`, `allow_methods=["*"]`, and `allow_headers=["*"]` are enabled with `allow_credentials=True`.
- Impact: This widens browser access to the API and can create dangerous behavior if cookie/session auth or credentialed browser requests are added later.
- Recommendation: Load allowed frontend origins from config and restrict methods/headers to what the app uses.

### Public group APIs expose user email addresses

- Files: `backend/app/schemas.py:21`, `backend/app/routers/groups.py:81`, `backend/app/routers/groups.py:119`
- Issue: `UserResponse` includes `email`, and group responses include `owner: UserResponse`; group member responses include `user: UserResponse`.
- Impact: Public group listing/details and member listing can disclose email addresses to users who should only need display names.
- Recommendation: Introduce public user schemas without email and use them for group owners, members, rankings, and other public surfaces.

### CSV formula injection in exports

- Files: `backend/app/routers/admin.py:523`, `backend/app/routers/groups.py:517`
- Issue: User-controlled fields such as display names, usernames, and emails are written directly to CSV cells.
- Impact: Spreadsheet apps may execute cells beginning with `=`, `+`, `-`, `@`, tab, or carriage return as formulas when an admin opens an export.
- Recommendation: Sanitize CSV cells by prefixing dangerous leading characters with a single quote, or use a dedicated CSV-safe export helper.

## Medium Severity

### Export endpoints opened from frontend without Authorization header

- Files: `frontend/src/pages/GroupDetails.jsx:144`, `frontend/src/pages/AdminPanel.jsx:336`
- Issue: Export buttons call `window.open(...)` directly.
- Impact: The Axios Bearer token interceptor is bypassed, so these requests likely fail with `401` unless another auth mechanism exists.
- Recommendation: Fetch the CSV with Axios as a blob, then create an object URL for download, or move auth to secure cookies with proper CSRF protection.

### Public registration has no rate limiting or abuse controls

- Files: `backend/app/routers/auth.py:13`, `backend/app/routers/auth.py:64`
- Issue: Register and login endpoints have no rate limiting, lockout, throttling, CAPTCHA, invite requirement, or email verification.
- Impact: The app is exposed to brute force attempts, user enumeration, spam registrations, and resource abuse.
- Recommendation: Add rate limiting per IP/account, normalize login errors where appropriate, and consider invite-only registration or email verification.

### Sync job auto-applies unconfirmed upstream match changes

- File: `backend/app/sync.py:304`
- Issue: The sync job fetches mutable GitHub-hosted data and automatically applies changes unless a match score was already admin-confirmed.
- Impact: Upstream data changes can alter fixtures, scores, and rankings without review.
- Recommendation: Require manual review for score changes, team substitutions, kickoff changes near match time, or any change affecting already locked matches.

### Development server mode in backend container

- File: `backend/Dockerfile:21`
- Issue: The backend container runs Uvicorn with `--reload`.
- Impact: `--reload` is intended for development, can spawn additional processes, and may duplicate startup side effects such as scheduler setup.
- Recommendation: Use a production command without reload, and run scheduled jobs as a separate process or guarded singleton.

## Bugs

### Group predictions CSV export crashes

- File: `backend/app/routers/groups.py:557`
- Issue: `func` is referenced but never imported. The interval expression is also unnecessarily database-specific.
- Impact: Calling `/api/groups/{group_id}/export/predictions` raises a server error.
- Recommendation: Replace the query with a Python threshold:

```python
locked_threshold = datetime.utcnow() + timedelta(hours=3)
locked_matches = db.query(Match).filter(Match.kickoff_time <= locked_threshold).all()
```

### Undefined `logger` in frontend error path

- File: `frontend/src/App.jsx:157`
- Issue: `refreshUser` calls `logger.error(...)`, but no `logger` variable is defined.
- Impact: If refresh fails, the error handler throws a new `ReferenceError`, hiding the original failure.
- Recommendation: Use `console.error(...)`, show UI feedback, or remove the log.

### Backend tests do not run with the default command

- File: `backend/app/tests/conftest.py:7`
- Issue: Running `pytest -q` from `backend/` fails with `ModuleNotFoundError: No module named 'app'`.
- Impact: The test suite is not runnable by default without setting `PYTHONPATH=.`, packaging the app, or adding pytest configuration.
- Recommendation: Add a `pytest.ini`/`pyproject.toml` test config that sets `pythonpath = .`, or install the backend package in editable mode for tests.

### Frontend build could not start in this checkout

- File: `frontend/package.json:7`
- Issue: `npm run build` failed with `vite: Permission denied` in this environment.
- Impact: The frontend build is not currently verifiable from this checkout.
- Recommendation: Reinstall frontend dependencies in the current environment or fix executable permissions for the Vite binary.

## Verification Notes

- `pytest -q` from `backend/` failed during collection because `app` was not importable.
- `PYTHONPATH=. pytest -q` got past that but failed in this environment because `python-jose` was not installed.
- `npm run build` from `frontend/` failed with `vite: Permission denied`.
