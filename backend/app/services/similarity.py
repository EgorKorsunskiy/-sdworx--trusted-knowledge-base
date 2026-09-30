from sqlalchemy.orm import Session

from app.models import Entry, EntryVersion, SystemSetting


def _tokens(text: str) -> set[str]:
    return set(
        word.lower()
        for word in text.replace(",", " ").replace(".", " ").split()
        if len(word) > 2
    )


def similarity(a: str, b: str) -> float:
    sa, sb = _tokens(a), _tokens(b)
    if not sa and not sb:
        return 1.0
    inter = sa & sb
    union = sa | sb
    if not union:
        return 0.0
    return len(inter) / len(union)


def find_similar(db: Session, title: str, body: str, threshold: float | None = None) -> list[dict]:
    if threshold is None:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "duplicate_similarity_threshold").first()
        threshold = float(setting.value) if setting else 0.6

    draft = f"{title} {body}"
    entries = db.query(Entry).join(Entry.versions).filter(Entry.is_published.is_(True)).all()
    matches: list[dict] = []
    for entry in entries:
        current = entry.versions[-1]
        existing = f"{current.title} {current.body}"
        score = similarity(draft, existing)
        if score >= threshold:
            matches.append({
                "public_id": entry.public_id,
                "title": current.title,
                "status": current.status,
                "score": round(score, 2),
            })
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches
