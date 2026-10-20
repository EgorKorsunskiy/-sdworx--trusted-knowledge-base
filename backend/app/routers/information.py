from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import get_current_user
from app.models import User
from app.services import information as info

router = APIRouter(prefix="/information", tags=["information"])


def _run(fn, *args, **kwargs):
    """Call a service function, turning its ParserError into the matching HTTP error."""
    try:
        return fn(*args, **kwargs)
    except info.ParserError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


class ApproveIn(BaseModel):
    basis: Literal["responsible", "relayed"]
    source: str | None = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class VoteIn(BaseModel):
    useful: bool


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Section counts and the number shown on the navigation item (FR-MS16): To decide plus Co-author requests."""
    counts = info.yours_counts(db, user, [])
    return {**counts, "badge": counts["to_decide"] + counts["coauthor"]}


@router.get("")
def overview(
    tab: Literal["yours", "others"] = "yours",
    section: Literal["to_decide", "postponed", "decided", "coauthor"] = "to_decide",
    kind: list[Literal["meeting", "chat"]] | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """The Information overview (FR-MS1 to FR-MS3, FR-MS10): one page of the Yours or Others tab.

    ``kind`` filters by Meetings and/or Group chats and applies to both tabs; none selected shows both."""
    kinds = kind or []
    if tab == "others":
        return {"tab": tab, "section": None, "counts": info.yours_counts(db, user, kinds),
                **info.paginate(info.others_items(db, user, kinds), page, page_size)}
    sections = info.yours_sections(db, user, kinds)
    counts = {name: len(items) for name, items in sections.items()}
    return {"tab": tab, "section": section, "counts": counts, **info.paginate(sections[section], page, page_size)}


@router.get("/locate")
def locate(
    suggestion: int | None = None,
    meme: int | None = None,
    request: int | None = None,
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Tab, section and page that show a suggestion, meme or co-author request (notification links)."""
    if suggestion is None and meme is None and request is None:
        raise HTTPException(status_code=422, detail="Give a suggestion, meme or request")
    return _run(info.locate, db, user, suggestion_id=suggestion, meme_id=meme, request_id=request, page_size=page_size)


@router.get("/memes/{meme_id}")
def get_meme(meme_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """One meme with quotes, decisions and history. Not found for anyone who did not take part (BR-M1)."""
    meme = _run(info.get_visible_meme, db, user, meme_id)
    return info.meme_out(db, meme, user)


@router.get("/suggestions/{suggestion_id}")
def get_suggestion(suggestion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    sug = _run(info.get_visible_suggestion, db, user, suggestion_id)
    return {"id": sug.id, "meme": info.meme_out(db, sug.meme, user)}


def _decide(db: Session, user: User, suggestion_id: int, action, *args) -> dict:
    sug = _run(info.get_own_suggestion, db, user, suggestion_id)
    _run(action, db, sug, *args)
    db.commit()
    db.refresh(sug)
    return {"id": sug.id, "meme": info.meme_out(db, sug.meme, user)}


@router.post("/suggestions/{suggestion_id}/approve")
def approve(suggestion_id: int, body: ApproveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Approve one's own suggestion with an authorship basis (FR-MO2, FR-MO15). Relayed needs a source."""
    return _decide(db, user, suggestion_id, info.approve, body.basis, body.source)


@router.post("/suggestions/{suggestion_id}/reject")
def reject(suggestion_id: int, body: RejectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _decide(db, user, suggestion_id, info.reject, body.reason)


@router.post("/suggestions/{suggestion_id}/postpone")
def postpone(suggestion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _decide(db, user, suggestion_id, info.postpone)


@router.post("/suggestions/{suggestion_id}/reopen")
def reopen(suggestion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _decide(db, user, suggestion_id, info.reopen)


@router.post("/suggestions/{suggestion_id}/withdraw")
def withdraw(suggestion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _decide(db, user, suggestion_id, info.withdraw)


@router.put("/memes/{meme_id}/vote")
def vote(meme_id: int, body: VoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Vote a meme useful or not useful; a second vote replaces the first (FR-MV1, FR-MV2)."""
    meme = _run(info.get_visible_meme, db, user, meme_id)
    _run(info.set_vote, db, meme, user, body.useful)
    db.commit()
    db.refresh(meme)
    return info.meme_out(db, meme, user)


@router.delete("/memes/{meme_id}/vote")
def withdraw_vote(meme_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    meme = _run(info.get_visible_meme, db, user, meme_id)
    _run(info.set_vote, db, meme, user, None)
    db.commit()
    db.refresh(meme)
    return info.meme_out(db, meme, user)


# ---- Add to repository (iteration 21) ----------------------------------------------------------------------------------


@router.get("/suggestions/{suggestion_id}/prefill")
def prefill(suggestion_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """What the Add entry form shows for an approved suggestion: the prefill, everyone's answers and the future
    co-authors. If another author saved first, ``already_published`` and the entry say so (FR-MS22, FR-MP7)."""
    from app.services import parser_publish

    sug = _run(info.get_own_suggestion, db, user, suggestion_id)
    if sug.meme.status != "published" and sug.state != "accepted":
        raise HTTPException(status_code=403, detail="Approve your suggestion first")
    return parser_publish.prefill(db, sug)


# ---- Co-authorship after publication (iteration 23) --------------------------------------------------------------------


class CoauthorRequestIn(BaseModel):
    basis: Literal["responsible", "relayed"]
    source: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)
    evidence: str | None = Field(default=None, max_length=500)


class DecisionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.post("/memes/{meme_id}/coauthor-requests", status_code=201)
def request_coauthorship(
    meme_id: int,
    body: CoauthorRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """A participant who is not an author asks the authors of a published meme for co-authorship (FR-MO10)."""
    from app.services import coauthors

    meme = _run(info.get_visible_meme, db, user, meme_id)
    _run(coauthors.request_coauthorship, db, meme, user, body.basis, body.source, body.note, body.evidence)
    db.commit()
    db.refresh(meme)
    return info.meme_out(db, meme, user)


def _decide_request(db: Session, user: User, request_id: int, accept: bool, reason: str | None) -> dict:
    from app.models import CoauthorRequest
    from app.services import coauthors

    req = db.get(CoauthorRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Not found")
    _run(info.get_visible_meme, db, user, req.meme_id)
    _run(coauthors.decide, db, req, user, accept, reason)
    db.commit()
    db.refresh(req)
    return {"request": info.request_out(req, user), "meme": info.meme_out(db, req.meme, user)}


@router.post("/coauthor-requests/{request_id}/accept")
def accept_request(
    request_id: int, body: DecisionIn | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return _decide_request(db, user, request_id, True, body.reason if body else None)


@router.post("/coauthor-requests/{request_id}/decline")
def decline_request(
    request_id: int, body: DecisionIn | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return _decide_request(db, user, request_id, False, body.reason if body else None)
