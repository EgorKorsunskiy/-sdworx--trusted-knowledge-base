from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import approvals, auth, categories, entries, health, outdated, search, similar, votes
from app.seeds import seed_all

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Token"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(entries.router)
app.include_router(approvals.router)
app.include_router(search.router)
app.include_router(votes.router)
app.include_router(outdated.router)
app.include_router(similar.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    seed_all()
