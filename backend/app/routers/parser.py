"""Upload a meeting transcript or chat export; the AI parser turns it into memes in the background.

Real uploads go to the database only (memes, authorship requests, notifications); the JSON files
in backend/memes/ are the demo output for the mock sources.
"""
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.ai_parser import pipeline, store
from app.ai_parser.sources import Source, load_chat, load_meeting, slug
from app.database import get_db
from app.deps.auth import get_current_user
from app.models import MemeSource, User

router = APIRouter(prefix="/parser", tags=["parser"])

# Run status, kept in memory: runs are short-lived and only their files matter afterwards
_runs: dict[str, dict] = {}


def _process(run_id: str, source: Source, upload_dir: Path, session_factory: sessionmaker) -> None:
    run = _runs[run_id]
    run["status"] = "running"
    db = session_factory()
    try:
        extraction = pipeline.extract(db, source)
        saved = store.save_extraction(db, extraction, uploaded_by_id=run["user_id"])
    except Exception as exc:  # any failure is reported on the run; the upload is kept for a retry
        db.rollback()
        run.update(status="failed", error=str(exc))
    else:
        run.update(status="done", memes=len(saved.memes), rejected=len(extraction.rejected))
        shutil.rmtree(upload_dir, ignore_errors=True)  # BR-M7: the raw source is not kept after extraction
    finally:
        db.close()


@router.post("/sources", status_code=202)
def upload_source(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    source_type: Literal["meeting", "chat"] = Form(..., alias="type"),
    title: str | None = Form(None),
    meeting_date: date | None = Form(None, alias="date"),
    participant_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    run_id = uuid.uuid4().hex[:12]
    upload_dir = config.MEMES_DIR / "_uploads" / run_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / Path(file.filename or f"source.{'vtt' if source_type == 'meeting' else 'json'}").name
    path.write_bytes(file.file.read())

    try:
        if source_type == "meeting":
            if not title or not meeting_date:
                raise HTTPException(status_code=422, detail="A meeting needs a title and a date")
            # The uploader is a participant (FR-MT1); unmatched speakers become guests
            people = db.query(User).filter(User.id.in_(set(participant_ids) | {user.id})).all()
            source = load_meeting(
                path, title.strip(), meeting_date, {u.email: u.display_name for u in people},
                source_id=f"{meeting_date.isoformat()}-{slug(title)}",
            )
        else:
            source = load_chat(path)
            source.id = slug(source.title)
            if user.email not in source.participants:
                raise HTTPException(status_code=403, detail="Only members of the chat can import it")
            pipeline.only_known_participants(db, source)
        if db.query(MemeSource).filter(MemeSource.key == source.id).first():
            raise HTTPException(status_code=409, detail=f"{source.title} has already been processed")
    except HTTPException:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    except (ValueError, KeyError) as exc:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"Could not read the {source_type}: {exc}") from exc

    _runs[run_id] = {
        "id": run_id,
        "status": "queued",
        "type": source_type,
        "source_id": source.id,
        "user_id": user.id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "memes": None,
        "rejected": None,
        "error": None,
    }
    # The request's session closes with the request; the job opens its own on the same database
    background.add_task(_process, run_id, source, upload_dir, sessionmaker(bind=db.get_bind()))
    return _public(_runs[run_id])


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(get_current_user)) -> dict:
    run = _runs.get(run_id)
    if run is None or run["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return _public(run)


def _public(run: dict) -> dict:
    return {k: v for k, v in run.items() if k != "user_id"}
