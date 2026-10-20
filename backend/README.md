# Peerpoint Backend

FastAPI + SQLite backend for the Peerpoint hackathon PoC.

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

## Database

New columns on existing tables are applied automatically at startup (`_ensure_columns` in `app/database.py`). To reset the database, stop the server and delete `backend/peerpoint.db`; it is recreated and re-seeded on the next start.

## Seed users

The database is auto-seeded on startup. Demo users:

| ID | Name | Roles |
|----|------|-------|
| 1 | Employee A | Employee (Payroll Consultant) |
| 2 | Employee B | Employee |
| 3 | Employee C | Employee |
| 4 | Senior Expert | Employee + Expert (Payroll dept) |
| 5 | Team Lead | Employee + Team Lead (own team) |
| 6 | Manager | Employee + Manager (own team) |
| 7 | Admin | Employee + Admin |

## Authentication

Sign-in is an OAuth2 authorization code flow with PKCE, followed by JWTs:

1. The frontend sends the browser to the identity provider (`/idp/authorize`, a built-in mock IdP, `idp_mode=mock`).
2. The IdP redirects back to `<frontend>/auth/callback?code=...`; the frontend posts the code and PKCE verifier to `POST /auth/token`.
3. Peerpoint verifies the IdP's id_token, matches the employee by e-mail (unknown or inactive employees get 403) and returns an RS256 **access token** (JWT, 15 min). A rotating **refresh token** is set as an HttpOnly cookie (8 h).
4. `POST /auth/refresh` renews the access token and rotates the refresh token; reusing an old refresh token revokes the whole token family. `POST /auth/logout` revokes it.

Every endpoint except the ones in `PUBLIC_PATHS` of `tests/test_auth.py` needs `Authorization: Bearer <access token>` (401 without, 403 without permission). Token lifetimes are the `access_token_minutes` / `refresh_token_hours` settings. Sign-in, refresh, sign-out and denied requests go to the append-only `audit_log` table (`GET /admin/audit-log`). Admins can force a sign-out with `POST /admin/users/{id}/revoke-tokens`.

Signing keys are generated into `backend/.keys/` on first start (git-ignored). `demo_mode` (default on) keeps the demo user picker (`/auth/users`, `/auth/dev-login`); set `DEMO_MODE=false` anywhere else. To use a real identity provider, replace `idp.exchange_code` in `app/services/idp.py` and set `IDP_MODE` to something other than `mock`.

## Endpoints

- `GET /health`
- `GET /auth/config`, `POST /auth/token`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- `GET /auth/users`, `POST /auth/dev-login` (demo mode only)
- `POST /entries`, `GET /entries/{public_id}`, `PATCH /entries/{public_id}`
