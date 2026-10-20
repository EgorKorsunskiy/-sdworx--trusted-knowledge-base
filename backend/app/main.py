from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.deps.auth import record_denied
from app.routers import admin, approvals, auth, categories, contributions, entries, health, history, idp, notifications, outdated, people, search, similar, votes
from app.seeds import seed_all, seed_history_demo, seed_people, seed_settings

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def audited_http_exception(request: Request, exc: HTTPException):
    if exc.status_code in (401, 403):
        record_denied(request, exc)
    return await http_exception_handler(request, exc)


app.include_router(health.router)
app.include_router(auth.router)
if settings.idp_mode == "mock":
    app.include_router(idp.router)
app.include_router(notifications.router)
app.include_router(contributions.router)
app.include_router(admin.router)
app.include_router(categories.router)
app.include_router(similar.router)  # before entries: /entries/similar must win over /entries/{public_id}
app.include_router(entries.router)
app.include_router(history.router)
app.include_router(approvals.router)
app.include_router(search.router)
app.include_router(votes.router)
app.include_router(outdated.router)
app.include_router(people.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    seed_all()
    seed_people()
    seed_settings()
    if settings.seed_history_demo:
        seed_history_demo()
