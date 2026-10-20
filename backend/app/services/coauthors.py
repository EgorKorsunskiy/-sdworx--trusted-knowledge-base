"""Co-authorship requests after publication (FR-MO10 to FR-MO15, BR-M2): a participant who is not an author asks the
authors; the first author to answer decides. Accepting creates no new version and keeps verification."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import CoauthorRequest, Meme, Quote, RequestStatus, SuggestionEvent, User
from app.services import contacts as contact_service
from app.services import information as info


def _author_ids(db: Session, meme: Meme) -> list[int]:
    return [p["user"].id for p in info.meme_authors(db, meme)]


def own_quote(meme: Meme, user: User) -> Quote | None:
    """The user's agent-detected quote if they were a candidate: their statement, else their confirmation."""
    mine = [q for q in meme.quotes if q.user_id == user.id]
    return mine[0] if mine else None


def request_coauthorship(
    db: Session,
    meme: Meme,
    user: User,
    basis: str,
    source: str | None,
    note: str | None,
    evidence: str | None,
) -> CoauthorRequest:
    blocked = info.request_blocker(db, meme, user)
    if blocked:
        raise info.ParserError(blocked, 409)
    try:
        basis, source = contact_service.clean_basis(basis, source)
    except contact_service.BasisError as exc:
        raise info.ParserError(str(exc), 422)
    quote = own_quote(meme, user)
    req = CoauthorRequest(
        meme_id=meme.id,
        requester_id=user.id,
        basis=basis,
        basis_source=source,
        note=" ".join((note or "").split())[:1000] or None,
        evidence=" ".join((evidence or "").split())[:500] or None,
        evidence_quote_id=quote.id if quote else None,
    )
    db.add(req)
    db.flush()
    for author_id in _author_ids(db, meme):
        info.notify(
            db, author_id, "coauthor_requested", "Co-authorship requested",
            f"{user.display_name} asks to be a co-author of “{meme.title}”.",
            f"/information?tab=yours&section=coauthor&request={req.id}",
        )
    return req


def decide(db: Session, req: CoauthorRequest, decider: User, accept: bool, reason: str | None) -> None:
    """Only a current author decides, and the first answer is final (FR-MO12)."""
    meme = req.meme
    if decider.id not in _author_ids(db, meme):
        raise info.ParserError("Only an author of this meme can decide on a co-authorship request", 403)
    if req.status != RequestStatus.PENDING.value:
        by = req.decided_by.display_name if req.decided_by else "another author"
        raise info.ParserError(f"This request was already decided by {by}", 409)
    now = datetime.utcnow()
    req.status = RequestStatus.ACCEPTED.value if accept else RequestStatus.DECLINED.value
    req.decided_by_id, req.decided_at = decider.id, now
    req.decision_reason = " ".join((reason or "").split())[:500] or None
    entry = meme.entry
    if accept:
        # The requester becomes a co-author: a contact and contributor, but no new version and no change of status
        contact_service.add_contact(db, entry, req.requester_id, req.basis, req.basis_source, role="co_author")
        mine = next((s for s in meme.suggestions if s.user_id == req.requester_id), None)
        if mine is not None:
            db.add(SuggestionEvent(suggestion_id=mine.id, action="joined", basis=req.basis, source=req.basis_source))
        info.notify(
            db, req.requester_id, "coauthor_decided", "You are a co-author",
            f"{decider.display_name} accepted your request for “{meme.title}”.",
            f"/entries/{entry.public_id}",
        )
    else:
        info.notify(
            db, req.requester_id, "coauthor_decided", "Co-authorship request declined",
            f"{decider.display_name} declined your request for “{meme.title}”.",
            f"/information?tab=others&meme={meme.id}",
        )
    db.flush()
