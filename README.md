# Peerpoint

Peer knowledge base for payroll / process guidance. Iterations 0–1: foundation + entries/versions.

## Stack

- **Backend:** FastAPI, SQLAlchemy 2, SQLite
- **Frontend:** Vite + React + TypeScript, Tailwind CSS v4, Lucide icons

## Quick start

### Backend

Use **Python 3.11** (3.14 wheels are incomplete for pydantic-core):

```bash
cd backend
/usr/local/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install 'pip==24.3.1'
pip install -r requirements.txt
# DB + seed also run on API startup
uvicorn app.main:app --reload --port 8000
```

Health: http://127.0.0.1:8000/health

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://127.0.0.1:5173 — Vite proxies `/api/*` → backend `:8000`.

Routes: `/login` (dev personas), `/` Search, `/add` Add entry, `/entries/:publicId` Entry page.

### Tests

```bash
cd backend && source .venv/bin/activate && pytest -q
```

## Demo users (dev login)

| Name | Email | Roles |
|------|-------|-------|
| Employee A | employee.a@sdworx.example | employee |
| Employee B | employee.b@sdworx.example | employee |
| Employee C | employee.c@sdworx.example | employee |
| Senior Expert | senior.expert@sdworx.example | employee, expert |
| Team Lead | team.lead@sdworx.example | employee, team_lead |
| Manager | manager@sdworx.example | employee, manager |
| Admin | admin@sdworx.example | employee, admin |

Seeded sample entry (Employee A, Unverified): **`PP-BE-FRE-00001`**

## Iteration 1 API

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/auth/dev-login` | `{ "user_id": N }` → cookie + `token` |
| `GET` | `/auth/users` | Dev login picker |
| `GET` | `/auth/me` | Current session |
| `GET` | `/categories` | Seeded categories |
| `POST` | `/entries` | Create entry + v1 (`Unverified`) |
| `GET` | `/entries/{public_id}` | Current version + metadata + who_to_ask |
| `GET` | `/entries/{public_id}/versions/{n}` | Historical version (read-only) |
| `PATCH` | `/entries/{public_id}` | Author-only edit of unverified current version |

**Public ID:** `PP-{CC}-{CAT}-{seq}` e.g. `PP-BE-FRE-00042` (stable across versions)

**Required create fields:** `title`, `body`, `category_id`, `country`  
**Scope:** `country-specific` \| `EU-wide` \| `universal`  
**Auto-tags:** `author:…`, `department:…`, `role:…`, `date:…` (+ keywords)

## Settings (seeded)

- Similarity threshold: **60%**
- Stale hint: **12 months**
- Expert vote weight: **1.3**
- Default category: **Freelance / contractor payroll**
