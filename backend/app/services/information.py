"""Information overview (AI parser): who sees what, and the decisions on suggestions.

Visibility is enforced here, server-side (BR-M1): only participants of a source can list or open its memes,
suggestions, decisions, history, quotes and context. Everyone else gets "not found".
"""

import json
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models import (
    CoauthorRequest,
    EntryContact,
    Meme,
    MemeStatus,
    Notification,
    RequestStatus,
    Source,
    SourceParticipant,
    Suggestion,
    SuggestionEvent,
    SuggestionState,
    UsageVote,
    User,
    Verification,
)
from app.services import contacts as contact_service
from app.services.scopes import scope_label

OPEN_STATES = (SuggestionState.PENDING.value, SuggestionState.POSTPONED.value)
SECTIONS = ("to_decide", "postponed", "decided", "coauthor")
STATE_LABEL = {
    SuggestionState.PENDING.value: "Pending",
    SuggestionState.POSTPONED.value: "Postponed",
    SuggestionState.ACCEPTED.value: "Approved",
    SuggestionState.DECLINED.value: "Rejected",
    SuggestionState.CLOSED.value: "Closed",
}


class ParserError(Exception):
    """A decision that is not allowed; ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


# --- visibility ----------------------------------------------------------------------------------------------------------


def participant_source_ids(db: Session, user: User) -> set[int]:
    return {sid for (sid,) in db.query(SourceParticipant.source_id).filter(SourceParticipant.user_id == user.id)}


def is_participant(db: Session, user: User, source_id: int) -> bool:
    return db.query(SourceParticipant.id).filter_by(source_id=source_id, user_id=user.id).first() is not None


def get_visible_meme(db: Session, user: User, meme_id: int) -> Meme:
    """The meme, or ParserError(404) when it does not exist or the user did not take part in its source."""
    meme = db.get(Meme, meme_id)
    if meme is None or not is_participant(db, user, meme.source_id):
        raise ParserError("Not found", 404)
    return meme


def get_visible_suggestion(db: Session, user: User, suggestion_id: int) -> Suggestion:
    sug = db.get(Suggestion, suggestion_id)
    if sug is None:
        raise ParserError("Not found", 404)
    get_visible_meme(db, user, sug.meme_id)
    return sug


def get_own_suggestion(db: Session, user: User, suggestion_id: int) -> Suggestion:
    """Only the owner decides on a suggestion (FR-MO22): a colleague's gets 403, a foreign source's 404."""
    sug = get_visible_suggestion(db, user, suggestion_id)
    if sug.user_id != user.id:
        raise ParserError("Only the owner of a suggestion can decide on it", 403)
    return sug


# --- authors -----------------------------------------------------------------------------------------------------------


def meme_authors(db: Session, meme: Meme) -> list[dict]:
    """Authors of a meme: the candidates who approved, and co-authors accepted after publication.

    Once published, the basis shown is the one on the entry's Contacts (an author can change it later, FR-MO17)."""
    people: list[dict] = []
    for s in meme.suggestions:
        if s.state == SuggestionState.ACCEPTED.value:
            people.append({"user": s.user, "basis": s.basis, "source": s.basis_source})
    for r in meme.coauthor_requests:
        if r.status == RequestStatus.ACCEPTED.value:
            people.append({"user": r.requester, "basis": r.basis, "source": r.basis_source})
    if meme.entry_id:
        contacts = {c.user_id: c for c in db.query(EntryContact).filter_by(entry_id=meme.entry_id)}
        for p in people:
            c = contacts.get(p["user"].id)
            if c is not None:
                p["basis"], p["source"] = c.basis, c.source
    return people


def is_author(db: Session, meme: Meme, user: User) -> bool:
    return any(p["user"].id == user.id for p in meme_authors(db, meme))


# --- status ------------------------------------------------------------------------------------------------------------


def recompute_status(meme: Meme) -> None:
    """New / Preparing / Declined follow the suggestions; Published is set only by saving the entry."""
    if meme.status == MemeStatus.PUBLISHED.value:
        return
    states = [s.state for s in meme.suggestions]
    if SuggestionState.ACCEPTED.value in states:
        meme.status = MemeStatus.PREPARING.value
    elif states and all(st == SuggestionState.DECLINED.value for st in states):
        meme.status = MemeStatus.DECLINED.value  # a postponed suggestion is undecided, not rejected
    else:
        meme.status = MemeStatus.NEW.value


def _log(db: Session, sug: Suggestion, action: str, basis=None, source=None, reason=None) -> None:
    db.add(SuggestionEvent(suggestion_id=sug.id, action=action, basis=basis, source=source, reason=reason))
    db.flush()
    db.refresh(sug)


def notify(db: Session, user_id: int, event: str, title: str, body: str, link: str) -> None:
    db.add(Notification(user_id=user_id, event_type=event, title=title, body=body, link=link))


def _ensure_open(sug: Suggestion) -> None:
    if sug.meme.status == MemeStatus.PUBLISHED.value or sug.state == SuggestionState.CLOSED.value:
        raise ParserError("This meme was already published; you can request co-authorship instead")
    if sug.meme.status == MemeStatus.DECLINED.value:
        raise ParserError("Every candidate rejected this meme")


# --- decisions (FR-MO2, FR-MO18, FR-MO21) ---------------------------------------------------------------------------


def approve(db: Session, sug: Suggestion, basis: str, source: str | None) -> None:
    _ensure_open(sug)
    if sug.state not in OPEN_STATES:
        raise ParserError("This suggestion is already decided")
    try:
        basis, source = contact_service.clean_basis(basis, source)
    except contact_service.BasisError as exc:
        raise ParserError(str(exc), 422)
    sug.state, sug.basis, sug.basis_source = SuggestionState.ACCEPTED.value, basis, source
    sug.decided_at = datetime.utcnow()
    _log(db, sug, "approve", basis=basis, source=source)
    recompute_status(sug.meme)
    _tell_other_candidates(db, sug, "approved")


def reject(db: Session, sug: Suggestion, reason: str | None) -> None:
    _ensure_open(sug)
    if sug.state not in OPEN_STATES:
        raise ParserError("This suggestion is already decided")  # a rejection is final, as is an approval's entry
    reason = " ".join((reason or "").split())[:500] or None
    sug.state, sug.decline_reason, sug.decided_at = SuggestionState.DECLINED.value, reason, datetime.utcnow()
    _log(db, sug, "reject", reason=reason)
    recompute_status(sug.meme)
    _tell_other_candidates(db, sug, "rejected")


def postpone(db: Session, sug: Suggestion) -> None:
    _ensure_open(sug)
    if sug.state != SuggestionState.PENDING.value:
        raise ParserError("Only a pending suggestion can be postponed")
    sug.state, sug.decided_at = SuggestionState.POSTPONED.value, datetime.utcnow()
    _log(db, sug, "postpone")  # silent: nobody is notified (FR-MN1)
    recompute_status(sug.meme)


def reopen(db: Session, sug: Suggestion) -> None:
    _ensure_open(sug)
    if sug.state != SuggestionState.POSTPONED.value:
        raise ParserError("Only a postponed suggestion can move back to To decide")
    sug.state, sug.decided_at = SuggestionState.PENDING.value, None
    _log(db, sug, "reopen")
    recompute_status(sug.meme)


def withdraw(db: Session, sug: Suggestion) -> None:
    _ensure_open(sug)
    if sug.state != SuggestionState.ACCEPTED.value:
        raise ParserError("Only an approval can be withdrawn")
    sug.state, sug.basis, sug.basis_source, sug.decided_at = SuggestionState.PENDING.value, None, None, None
    _log(db, sug, "withdraw")
    recompute_status(sug.meme)  # back to New when no author remains (FR-MO8)


def _tell_other_candidates(db: Session, sug: Suggestion, verb: str) -> None:
    meme = sug.meme
    for other in meme.suggestions:
        if other.user_id != sug.user_id:
            notify(
                db, other.user_id, "candidate_decided",
                f"A co-candidate {verb} their suggestion",
                f"{sug.user.display_name} {verb} “{meme.title}”.",
                f"/information?tab=others&meme={meme.id}&history=1",
            )


def close_open_suggestions(db: Session, meme: Meme) -> None:
    """The entry was saved: pending and postponed suggestions are closed and their owners told (FR-MO7)."""
    for s in meme.suggestions:
        if s.state in OPEN_STATES:
            s.state, s.decided_at = SuggestionState.CLOSED.value, datetime.utcnow()
            _log(db, s, "closed", reason="Published by another author")
            notify(
                db, s.user_id, "meme_published", "Published without you",
                f"“{meme.title}” was added to the repository. You can still request co-authorship.",
                f"/information?tab=yours&section=decided&suggestion={s.id}",
            )


# --- co-authorship eligibility (FR-MS19, BR-M2) -------------------------------------------------------------------------


def request_blocker(db: Session, meme: Meme, user: User) -> str | None:
    """Why this participant cannot request co-authorship of a published meme right now, or None."""
    if meme.status != MemeStatus.PUBLISHED.value or meme.entry_id is None:
        return "Co-authorship can be requested once the meme is published"
    if is_author(db, meme, user):
        return "You are already an author"
    mine = next((r for r in meme.coauthor_requests if r.requester_id == user.id), None)
    if mine is not None:
        if mine.status == RequestStatus.PENDING.value:
            return "You already have an open request for this meme"
        if mine.status == RequestStatus.DECLINED.value:
            return "An earlier request was declined and cannot be repeated"
    entry = meme.entry
    version_ids = [v.id for v in entry.versions]
    has_vote = (
        db.query(UsageVote.id)
        .filter(UsageVote.user_id == user.id, UsageVote.version_id.in_(version_ids), UsageVote.withdrawn_at.is_(None))
        .first()
    )
    if has_vote:
        return "You have a usage vote on this entry. Withdraw it first"
    verified = (
        db.query(Verification.id)
        .filter(
            Verification.verifier_id == user.id,
            Verification.action == "verify",
            Verification.version_id == entry.versions[-1].id,
        )
        .first()
    )
    if verified:
        return "You verified the current version, so you cannot become its author"
    return None


# --- output -------------------------------------------------------------------------------------------------------------


def _person(u: User) -> dict:
    return {"id": u.id, "display_name": u.display_name, "title": u.title, "department": u.department}


def suggestion_out(s: Suggestion, viewer: User) -> dict:
    published = s.meme.status == MemeStatus.PUBLISHED.value
    if s.state == SuggestionState.ACCEPTED.value:
        label = "Approved" if published else "Approved, not yet added"
    elif s.state == SuggestionState.CLOSED.value:
        label = "Closed: published without you"
    else:
        label = STATE_LABEL[s.state]
    return {
        "id": s.id,
        "owner": _person(s.user),
        "is_mine": s.user_id == viewer.id,
        "role": s.role,
        "state": s.state,
        "label": label,
        "basis": s.basis,
        "source": s.basis_source,
        "reason": s.decline_reason,
        "decided_at": s.decided_at,
        "basis_hint": json.loads(s.basis_hint_json) if s.basis_hint_json else None,
        "history": [
            {
                "id": e.id,
                "action": e.action,
                "basis": e.basis,
                "source": e.source,
                "reason": e.reason,
                "created_at": e.created_at,
            }
            for e in s.events
        ],
    }


def request_out(r: CoauthorRequest, viewer: User) -> dict:
    return {
        "id": r.id,
        "requester": _person(r.requester),
        "basis": r.basis,
        "source": r.basis_source,
        "note": r.note,
        "evidence": r.evidence,
        "evidence_quote": ({"text": r.evidence_quote.text, "at": r.evidence_quote.at} if r.evidence_quote else None),
        "status": r.status,
        "decided_by": _person(r.decided_by) if r.decided_by else None,
        "decision_reason": r.decision_reason,
        "decided_at": r.decided_at,
        "created_at": r.created_at,
        "is_mine": r.requester_id == viewer.id,
    }


def meme_out(db: Session, meme: Meme, viewer: User) -> dict:
    """A meme as a participant sees it: statement, people, decisions with history, quotes with context."""
    src = meme.source
    mine = next((s for s in meme.suggestions if s.user_id == viewer.id), None)
    authors = meme_authors(db, meme)
    viewer_is_author = any(p["user"].id == viewer.id for p in authors)
    published = meme.status == MemeStatus.PUBLISHED.value
    my_request = next((r for r in meme.coauthor_requests if r.requester_id == viewer.id), None)
    return {
        "id": meme.id,
        "title": meme.title,
        "statement": meme.statement,
        "kind": meme.kind,
        "status": meme.status,
        "sensitive": meme.sensitive,
        "category": meme.category_name,
        "country": meme.country,
        "scope": meme.scope,
        "scope_label": scope_label(meme.scope, meme.company, meme.client_project),
        "company": {"id": meme.company.id, "name": meme.company.name} if meme.company else None,
        "client_project": (
            {"id": meme.client_project.id, "name": meme.client_project.name, "company": meme.client_project.company.name}
            if meme.client_project else None
        ),
        "tags": [{"id": t.id, "name": t.name, "tag_type": t.tag_type} for t in meme.tags],
        "similar_entries": json.loads(meme.similar_json) if meme.similar_json else [],
        "source": {
            "id": src.id,
            "kind": src.kind,
            "title": src.title,
            "date_from": src.date_from,
            "date_to": src.date_to,
        },
        "speaker": _person(meme.speaker),
        "confirmers": [_person(s.user) for s in meme.suggestions if s.role == "confirmer"],
        "quotes": [
            {
                "id": q.id,
                "user": _person(q.user),
                "text": q.text,
                "at": q.at,
                "is_confirmation": q.is_confirmation,
                "context": json.loads(q.context_json) if q.context_json else [],
            }
            for q in meme.quotes
        ],
        "suggestions": [suggestion_out(s, viewer) for s in meme.suggestions],
        "my_suggestion_id": mine.id if mine else None,
        "entry": (
            {"public_id": meme.entry.public_id, "status": meme.entry.versions[-1].status}
            if published and meme.entry else None
        ),
        "authors": [
            {"user": _person(p["user"]), "basis": p["basis"], "source": p["source"], "is_me": p["user"].id == viewer.id}
            for p in authors
        ],
        "is_author": viewer_is_author,
        "is_candidate": mine is not None,
        "can_request_coauthorship": published and not viewer_is_author,
        "request_blocked_reason": request_blocker(db, meme, viewer) if published and not viewer_is_author else None,
        "my_request": request_out(my_request, viewer) if my_request else None,
        "pending_requests": [
            request_out(r, viewer)
            for r in meme.coauthor_requests
            if viewer_is_author and published and r.status == RequestStatus.PENDING.value and r.requester_id != viewer.id
        ],
    }


# --- listing (FR-MS1 to FR-MS16) ---------------------------------------------------------------------------------------------


def _visible_memes(db: Session, user: User, kinds: list[str]) -> list[Meme]:
    ids = participant_source_ids(db, user)
    if not ids:
        return []
    q = db.query(Meme).join(Source, Source.id == Meme.source_id).filter(Meme.source_id.in_(ids))
    if kinds:
        q = q.filter(Source.kind.in_(kinds))
    return q.options(
        joinedload(Meme.source),
        joinedload(Meme.speaker),
        joinedload(Meme.suggestions).joinedload(Suggestion.user),
    ).all()


def _newest_first(meme: Meme):
    return (meme.source.date_from, meme.id)


def _pending_requests(db: Session, user: User, memes: list[Meme]) -> list[tuple[Meme, CoauthorRequest]]:
    """Open co-author requests addressed to the user as an author of a published meme (FR-MS18)."""
    return [
        (m, r)
        for m in memes
        if m.status == MemeStatus.PUBLISHED.value and is_author(db, m, user)
        for r in m.coauthor_requests
        if r.status == RequestStatus.PENDING.value and r.requester_id != user.id
    ]


def _decided_requests(db: Session, user: User, memes: list[Meme]) -> list[tuple[Meme, CoauthorRequest]]:
    return [
        (m, r)
        for m in memes
        if is_author(db, m, user)
        for r in m.coauthor_requests
        if r.status != RequestStatus.PENDING.value
    ]


def yours_sections(db: Session, user: User, kinds: list[str]) -> dict[str, list]:
    """The four sections of the Yours tab as unpaged item lists, newest source first."""
    memes = _visible_memes(db, user, kinds)
    mine = sorted(
        [(m, s) for m in memes for s in m.suggestions if s.user_id == user.id],
        key=lambda pair: _newest_first(pair[0]),
        reverse=True,
    )

    # Items are (type, id, builder): the builder renders one only when its page is requested
    def suggestion_item(meme: Meme, sug: Suggestion):
        return ("suggestion", sug.id, lambda: {"type": "suggestion", "id": sug.id, "meme": meme_out(db, meme, user)})

    def request_item(meme: Meme, req: CoauthorRequest):
        return ("coauthor_request", req.id, lambda: {
            "type": "coauthor_request", "id": req.id, "meme": meme_out(db, meme, user), "request": request_out(req, user)
        })

    decided = [(s.decided_at or datetime.min, suggestion_item(m, s)) for m, s in mine if s.state not in OPEN_STATES]
    decided += [(r.decided_at or datetime.min, request_item(m, r)) for m, r in _decided_requests(db, user, memes)]
    decided.sort(key=lambda pair: pair[0], reverse=True)
    return {
        "to_decide": [suggestion_item(m, s) for m, s in mine if s.state == SuggestionState.PENDING.value],
        "postponed": [suggestion_item(m, s) for m, s in mine if s.state == SuggestionState.POSTPONED.value],
        "decided": [item for _, item in decided],
        "coauthor": [
            request_item(m, r) for m, r in sorted(_pending_requests(db, user, memes), key=lambda p: p[1].created_at)
        ],
    }


def yours_counts(db: Session, user: User, kinds: list[str]) -> dict:
    """Section counts for the tabs and the navigation badge."""
    memes = _visible_memes(db, user, kinds)
    states = [s.state for m in memes for s in m.suggestions if s.user_id == user.id]
    return {
        "to_decide": states.count(SuggestionState.PENDING.value),
        "postponed": states.count(SuggestionState.POSTPONED.value),
        "decided": sum(1 for st in states if st not in OPEN_STATES) + len(_decided_requests(db, user, memes)),
        "coauthor": len(_pending_requests(db, user, memes)),
    }


def others_items(db: Session, user: User, kinds: list[str]) -> list:
    """Memes of the user's sources for which other users own suggestions (FR-MS13, FR-MS15)."""
    items = []
    for meme in sorted(_visible_memes(db, user, kinds), key=_newest_first, reverse=True):
        if any(s.user_id != user.id for s in meme.suggestions):
            items.append(
                ("meme", meme.id, lambda meme=meme: {"type": "meme", "id": meme.id, "meme": meme_out(db, meme, user)})
            )
    return items


def paginate(items: list, page: int, page_size: int) -> dict:
    """One page of lazily built items (default 10 per page), with the total count (FR-MS10)."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)
    start = (page - 1) * page_size
    return {"items": [build() for _, _, build in items[start:start + page_size]], "total": len(items),
            "page": page, "page_size": page_size}


def locate(
    db: Session,
    user: User,
    *,
    suggestion_id: int | None = None,
    meme_id: int | None = None,
    request_id: int | None = None,
    page_size: int = 10,
) -> dict:
    """Where an item sits in the overview (tab, section, page), so a notification opens the right view (FR-MS23)."""
    if request_id is not None:
        req = db.get(CoauthorRequest, request_id)
        if req is None:
            raise ParserError("Not found", 404)
        meme = get_visible_meme(db, user, req.meme_id)
        sections = yours_sections(db, user, [])
        for name in ("coauthor", "decided"):
            ids = [(t, i) for t, i, _ in sections[name]]
            if ("coauthor_request", req.id) in ids:
                return {"tab": "yours", "section": name, "page": ids.index(("coauthor_request", req.id)) // page_size + 1}
        meme_id = meme.id
    if suggestion_id is not None:
        sug = get_visible_suggestion(db, user, suggestion_id)
        if sug.user_id == user.id:
            sections = yours_sections(db, user, [])
            for name in ("to_decide", "postponed", "decided"):
                ids = [(t, i) for t, i, _ in sections[name]]
                if ("suggestion", sug.id) in ids:
                    return {"tab": "yours", "section": name, "page": ids.index(("suggestion", sug.id)) // page_size + 1}
        meme_id = sug.meme_id
    meme = get_visible_meme(db, user, meme_id)
    ids = [i for _, i, _ in others_items(db, user, [])]
    if meme.id in ids:
        return {"tab": "others", "section": None, "page": ids.index(meme.id) // page_size + 1}
    return {"tab": "yours", "section": "to_decide", "page": 1}


def badge_count(db: Session, user: User) -> int:
    c = yours_counts(db, user, [])
    return c["to_decide"] + c["coauthor"]
