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

## Endpoints

- `GET /health`
- `GET /auth/users`
- `POST /auth/dev-login`
- `GET /auth/me`
- `POST /auth/logout`
- `POST /entries`, `GET /entries/{public_id}`, `PATCH /entries/{public_id}`
