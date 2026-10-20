"""Tags are shared entities: a unique, normalized name and a type.

* ``keyword`` tags are set by people.
* ``automatic`` tags are set by the system from the entry itself and use a ``kind:value`` name
  (country, date, author, department, role). People cannot create or rename them.
"""

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Entry, Tag, entry_tags

KEYWORD = "keyword"
AUTOMATIC = "automatic"
AUTO_KINDS = ("country", "date", "author", "department", "role")
AUTO_PREFIXES = tuple(f"{kind}:" for kind in AUTO_KINDS)
MAX_TAG_LENGTH = 64


class TagError(ValueError):
    """Invalid tag name or operation; the message is safe to show to the user."""


def normalize_tag(name: str | None) -> str:
    """Lowercase, trimmed, inner whitespace collapsed to single spaces. May return ''."""
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def is_automatic_name(name: str) -> bool:
    return normalize_tag(name).startswith(AUTO_PREFIXES)


def auto_tag_name(kind: str, value: str | None) -> str:
    return normalize_tag(f"{kind}:{value or 'unknown'}")


def validate_keyword(name: str | None) -> str:
    """Normalized keyword name, or TagError. Keywords may not use the reserved automatic prefixes."""
    normalized = normalize_tag(name)
    if not normalized:
        raise TagError("A tag cannot be empty")
    if len(normalized) > MAX_TAG_LENGTH:
        raise TagError(f"A tag can be at most {MAX_TAG_LENGTH} characters")
    if is_automatic_name(normalized):
        raise TagError(f"Tags starting with {', '.join(AUTO_PREFIXES)} are set by the system")
    return normalized


def get_or_create_tag(db: Session, name: str, tag_type: str = KEYWORD) -> Tag:
    """The existing tag with this normalized name, or a new one. A new tag is created only when none matches."""
    normalized = normalize_tag(name)
    tag = db.query(Tag).filter(Tag.name == normalized).first()
    if tag is None:
        tag = Tag(name=normalized, tag_type=tag_type)
        db.add(tag)
        db.flush()
    return tag


def add_keywords(db: Session, entry: Entry, keywords: list[str]) -> None:
    """Link people-set keywords to an entry, reusing existing tags (raises TagError on a bad name)."""
    have = {t.id for t in entry.tags}
    for raw in keywords:
        if not normalize_tag(raw):
            continue  # blank entries are ignored, as before
        tag = get_or_create_tag(db, validate_keyword(raw), KEYWORD)
        if tag.id not in have:
            entry.tags.append(tag)
            have.add(tag.id)


def add_auto_tags(db: Session, entry: Entry, author) -> None:
    """The system tags every entry carries: country, date, author, department and role."""
    role = author.roles[0].role if author.roles else "employee"
    names = [
        auto_tag_name("author", author.display_name),
        auto_tag_name("department", author.department),
        auto_tag_name("role", role),
        auto_tag_name("date", entry.created_at.date().isoformat() if entry.created_at else None),
    ]
    if entry.country:
        names.append(auto_tag_name("country", entry.country))
    have = {t.name for t in entry.tags}
    for name in names:
        if name not in have:
            entry.tags.append(get_or_create_tag(db, name, AUTOMATIC))
            have.add(name)


def usage_count(db: Session, tag_id: int) -> int:
    return db.query(func.count()).select_from(entry_tags).filter(entry_tags.c.tag_id == tag_id).scalar() or 0


def suggest_tags(db: Session, q: str | None, tag_type: str | None = None, limit: int = 10) -> list[dict]:
    """Existing tags matching ``q`` (prefix matches first), most used first."""
    needle = normalize_tag(q)
    counts = (
        db.query(entry_tags.c.tag_id, func.count().label("n")).group_by(entry_tags.c.tag_id).subquery()
    )
    query = db.query(Tag, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.tag_id == Tag.id)
    if tag_type:
        query = query.filter(Tag.tag_type == tag_type)
    if needle:
        query = query.filter(Tag.name.like(f"%{needle}%"))
    rows = query.all()
    rows.sort(key=lambda r: (needle and not r[0].name.startswith(needle), -r[1], r[0].name))
    return [{"id": t.id, "name": t.name, "tag_type": t.tag_type, "entry_count": n} for t, n in rows[:limit]]


def rename_tag(db: Session, tag: Tag, new_name: str) -> Tag:
    """Admin rename of a keyword tag. Links to entries are kept (same row)."""
    if tag.tag_type != KEYWORD:
        raise TagError("Automatic tags are set by the system and cannot be renamed")
    normalized = validate_keyword(new_name)
    clash = db.query(Tag).filter(Tag.name == normalized, Tag.id != tag.id).first()
    if clash is not None:
        raise TagError(f"A tag named '{normalized}' already exists; merge the tags instead")
    tag.name = normalized
    db.flush()
    return tag


def merge_tags(db: Session, source: Tag, target: Tag) -> Tag:
    """Admin merge of two keyword tags: every entry of ``source`` ends up linked to ``target``."""
    if source.id == target.id:
        raise TagError("Choose a different tag to merge into")
    if source.tag_type != KEYWORD or target.tag_type != KEYWORD:
        raise TagError("Only keyword tags can be merged")
    already = {r[0] for r in db.query(entry_tags.c.entry_id).filter(entry_tags.c.tag_id == target.id)}
    for (entry_id,) in db.query(entry_tags.c.entry_id).filter(entry_tags.c.tag_id == source.id).all():
        if entry_id not in already:
            db.execute(entry_tags.insert().values(entry_id=entry_id, tag_id=target.id))
    db.execute(entry_tags.delete().where(entry_tags.c.tag_id == source.id))
    db.delete(source)
    db.flush()
    return target


def normalize_existing_tags(db: Session) -> int:
    """One-off cleanup of tags created before tags were entities: normalize names (merging tags that
    collide), set the type of automatic tags and add the missing country tags. Idempotent."""
    changed = 0
    for tag in db.query(Tag).order_by(Tag.id).all():
        normalized = normalize_tag(tag.name) or tag.name
        wanted_type = AUTOMATIC if normalized.startswith(AUTO_PREFIXES) else tag.tag_type or KEYWORD
        if normalized != tag.name:
            clash = db.query(Tag).filter(Tag.name == normalized, Tag.id != tag.id).first()
            if clash is not None:
                # Same tag in two spellings: move the links and drop the duplicate.
                have = {r[0] for r in db.query(entry_tags.c.entry_id).filter(entry_tags.c.tag_id == clash.id)}
                for (entry_id,) in db.query(entry_tags.c.entry_id).filter(entry_tags.c.tag_id == tag.id).all():
                    if entry_id not in have:
                        db.execute(entry_tags.insert().values(entry_id=entry_id, tag_id=clash.id))
                db.execute(entry_tags.delete().where(entry_tags.c.tag_id == tag.id))
                db.delete(tag)
                db.flush()
                changed += 1
                continue
            tag.name = normalized
            changed += 1
        if tag.tag_type != wanted_type:
            tag.tag_type = wanted_type
            changed += 1
    db.flush()
    for entry in db.query(Entry).filter(Entry.country.isnot(None)).all():
        name = auto_tag_name("country", entry.country)
        if not any(t.name == name for t in entry.tags):
            entry.tags.append(get_or_create_tag(db, name, AUTOMATIC))
            changed += 1
    db.commit()
    return changed
