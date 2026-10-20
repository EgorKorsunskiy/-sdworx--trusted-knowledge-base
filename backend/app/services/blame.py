"""Per-line responsibility ("git blame" for entry bodies, BR-7). Pure: no DB / ORM imports."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.services.diff import diff_body, split_fragments_ex


@dataclass(frozen=True)
class VersionSnap:
    number: int
    body: str
    editor_id: int


@dataclass(frozen=True)
class BlameLine:
    index: int
    sep: str
    text: str
    contributor_ids: tuple[int, ...]
    introduced_in: int
    last_edited_in: int


def compute_blame(snaps: Sequence[VersionSnap]) -> list[BlameLine]:
    """Blame of the last snapshot. Snaps are ordered oldest -> newest; title/justification are ignored."""
    prev: list[tuple[str, tuple[int, ...], int, int]] = []  # (text, ids, introduced, last)
    prev_body = ""
    for n, snap in enumerate(snaps):
        if n == 0:
            cur = [
                (t, (snap.editor_id,), snap.number, snap.number)
                for _, t in split_fragments_ex(snap.body)
            ]
        else:
            cur = []
            i = 0
            for f in diff_body(prev_body, snap.body):
                kind = f["type"]
                if kind == "equal":
                    cur.append(prev[i])
                    i += 1
                elif kind == "edited":
                    text, ids, intro, _ = prev[i]
                    i += 1
                    if snap.editor_id not in ids:
                        ids = ids + (snap.editor_id,)
                    cur.append((f["new_text"], ids, intro, snap.number))
                elif kind == "removed":
                    i += 1
                else:  # added
                    cur.append((f["new_text"], (snap.editor_id,), snap.number, snap.number))
        prev, prev_body = cur, snap.body
    seps = [s for s, _ in split_fragments_ex(prev_body)]
    return [
        BlameLine(i, seps[i], t, ids, intro, last) for i, (t, ids, intro, last) in enumerate(prev)
    ]


def contributor_stats(lines: Sequence[BlameLine]) -> list[dict]:
    by_user: dict[int, list[BlameLine]] = {}
    for line in lines:
        for uid in line.contributor_ids:
            by_user.setdefault(uid, []).append(line)
    stats = [
        {
            "user_id": uid,
            "fragment_indexes": [l.index for l in ls],
            "fragment_count": len(ls),
            "first_version": min(l.introduced_in for l in ls),
            "last_version": max(l.last_edited_in for l in ls),
        }
        for uid, ls in by_user.items()
    ]
    stats.sort(key=lambda s: (-s["fragment_count"], s["first_version"], s["user_id"]))
    return stats
