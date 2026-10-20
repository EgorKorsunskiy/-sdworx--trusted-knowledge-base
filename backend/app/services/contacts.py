"""Authorship basis and contacts (FR-K, BR-10). DB only; callers commit."""

from sqlalchemy.orm import Session, joinedload

from app.models import Basis, Entry, EntryContact, EntryContactChange, User

BASES = (Basis.RESPONSIBLE.value, Basis.RELAYED.value)
MAX_SOURCE = 500


class BasisError(ValueError):
    """A basis that cannot be saved; the message is shown to the user."""


def clean_basis(basis: str | None, source: str | None) -> tuple[str, str | None]:
    """Validate a basis: Responsible needs nothing, Relayed needs a source (FR-K1). Returns the stored pair."""
    basis = (basis or "").strip().lower()
    if basis not in BASES:
        raise BasisError("State your authorship basis: Responsible or Relayed")
    source = " ".join((source or "").split()) or None
    if basis == Basis.RELAYED.value:
        if source is None:
            raise BasisError("A relayed basis needs a source (document, link, regulation, newsletter or colleague)")
        if len(source) > MAX_SOURCE:
            raise BasisError(f"The source must be at most {MAX_SOURCE} characters")
        return basis, source
    return basis, None  # a source only belongs to a relayed basis


def get_contact(db: Session, entry_id: int, user_id: int) -> EntryContact | None:
    return db.query(EntryContact).filter_by(entry_id=entry_id, user_id=user_id).first()


def add_contact(
    db: Session, entry: Entry, user_id: int, basis: str, source: str | None, role: str
) -> EntryContact:
    """Make a person a contact of the entry with a basis. A person who already is one keeps their row."""
    basis, source = clean_basis(basis, source)
    existing = get_contact(db, entry.id, user_id)
    if existing is not None:
        return existing
    contact = EntryContact(entry_id=entry.id, user_id=user_id, role=role, basis=basis, source=source)
    db.add(contact)
    db.flush()
    return contact


def change_basis(db: Session, entry: Entry, user: User, basis: str, source: str | None) -> EntryContact:
    """A person changes their own basis (FR-K2): logged, no new version, verification untouched."""
    contact = get_contact(db, entry.id, user.id)
    if contact is None:
        raise LookupError("You are not an author or contributor of this entry")
    basis, source = clean_basis(basis, source)
    if (contact.basis, contact.source) == (basis, source):
        return contact
    db.add(EntryContactChange(
        entry_id=entry.id,
        user_id=user.id,
        old_basis=contact.basis,
        old_source=contact.source,
        new_basis=basis,
        new_source=source,
    ))
    contact.basis, contact.source = basis, source
    db.flush()
    return contact


def active_contacts(entry: Entry) -> list[EntryContact]:
    """Contacts as readers see them: people who left the company are not shown (FR-K5).
    Responsible ones first, then relayed ones; the creator before co-authors and contributors."""
    order = {"author": 0, "co_author": 1, "contributor": 2}
    rows = [c for c in entry.contacts if c.user.is_active]
    rows.sort(key=lambda c: (c.basis != Basis.RESPONSIBLE.value, order.get(c.role, 3), c.id))
    return rows


def has_responsible_contact(entry: Entry) -> bool:
    return any(c.basis == Basis.RESPONSIBLE.value for c in active_contacts(entry))


def contact_user_ids(db: Session, entry_id: int) -> set[int]:
    """Everyone listed as a contact, co-authors from the AI parser included: they may neither vote on nor verify."""
    rows = db.query(EntryContact.user_id).filter(EntryContact.entry_id == entry_id).all()
    return {uid for (uid,) in rows}


def contact_options():
    return [joinedload(Entry.contacts).joinedload(EntryContact.user)]


def backfill_author_contacts(db: Session) -> int:
    """Entries from before authorship bases existed: the creator is listed as Responsible (idempotent)."""
    have = {eid for (eid,) in db.query(EntryContact.entry_id).filter(EntryContact.role == "author")}
    added = 0
    for entry in db.query(Entry).all():
        if entry.id in have:
            continue
        db.add(EntryContact(
            entry_id=entry.id,
            user_id=entry.author_id,
            role="author",
            basis=Basis.RESPONSIBLE.value,
            created_at=entry.created_at,
        ))
        added += 1
    db.commit()
    return added
