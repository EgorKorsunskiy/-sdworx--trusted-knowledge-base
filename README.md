# Peerpoint

Internal knowledge base with human trust signals. Hackathon MVP covering Iterations 0–7.

## Stack

- **Backend:** FastAPI + SQLAlchemy 2 + SQLite (Python 3.11)
- **Frontend:** Vite + React + TypeScript + Tailwind CSS + Lucide icons

## Quick start

### Backend

```bash
cd backend
/usr/local/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --reload --port 8001
```

Health: http://127.0.0.1:8001/health

If port 8000 is free you can use 8000; the frontend proxy is set to 8001.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and pick a demo user.

### Tests

```bash
cd backend && source .venv/bin/activate && pytest -q
```

## Demo users

| Name | Roles |
|------|-------|
| Employee A | employee |
| Employee B | employee |
| Employee C | employee |
| Senior Expert | employee, expert (Payroll dept) |
| Team Lead | employee, team_lead (own team) |
| Manager | employee, manager (own team) |
| Admin | employee, admin |

## Iterations implemented

- **0:** FastAPI + SQLite schema, seed data, React + Tailwind shell, dev login
- **1:** Entries, versions, public IDs, add-entry form, entry page
- **2:** Approval tab with dual-scope verification (dept experts + own-team TL/manager)
- **3:** Ranked search
- **4:** Usage-record votes (when/where/correct), reputation, incorrect-vote notifications
- **5:** Outdated flags and verifier confirmation
- **6:** Keyword duplicate-detection warning on add entry
- **7:** In-app notifications, My contributions, Admin panel

## Notes

- Scope values: `country`, `eu`, `universal`
- Public ID format: `PP-{CC}-{CAT}-{seq}` e.g. `PP-BE-FRE-00042`
