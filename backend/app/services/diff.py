"""Version diffs: pure helpers (no DB) plus approver lookup.

Reusable for pull requests: build_diff(snapshot(current), {title, body, justification}, author, meta).
"""

import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models import EntryVersion, PRApproval, Verification

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_fragments_ex(text: str | None) -> list[tuple[str, str]]:
    """Like split_fragments but returns (separator_before, fragment).

    The separator is '' for the first fragment, the matched whitespace between sentences of one line,
    or '\\n' * k across lines (k = newlines since the previous fragment; blank lines give '\\n\\n').
    """
    if not text:
        return []
    out: list[tuple[str, str]] = []
    pending = 0
    for idx, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
        if idx > 0:
            pending += 1
        line = line.strip()
        if not line:
            continue
        sep = "\n" * pending if out else ""
        pending = 0
        last = 0
        for m in _SENTENCE_END.finditer(line):
            out.append((sep, line[last : m.start()]))
            sep, last = m.group(), m.end()
        out.append((sep, line[last:]))
    return out


def split_fragments(text: str | None) -> list[str]:
    """Split a body into fragments: one per line, and one per sentence within a line."""
    return [t for _, t in split_fragments_ex(text)]


def snapshot(v: EntryVersion | None) -> dict:
    if v is None:
        return {"title": "", "body": "", "justification": None}
    return {"title": v.title, "body": v.body or "", "justification": v.justification}


def user_ref(u) -> dict:
    return {"id": u.id, "display_name": u.display_name, "title": u.title}


def _word_parts(old: str, new: str) -> list[dict]:
    a, b = old.split(" "), new.split(" ")
    parts: list[dict] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            parts.append({"op": "equal", "text": " ".join(a[i1:i2])})
        else:
            if i2 > i1:
                parts.append({"op": "delete", "text": " ".join(a[i1:i2])})
            if j2 > j1:
                parts.append({"op": "insert", "text": " ".join(b[j1:j2])})
    return parts


def diff_body(old: str | None, new: str | None) -> list[dict]:
    a, b = split_fragments(old), split_fragments(new)
    out: list[dict] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out += [{"type": "equal", "old_text": t, "new_text": t} for t in a[i1:i2]]
        elif tag == "delete":
            out += [{"type": "removed", "old_text": t, "new_text": None} for t in a[i1:i2]]
        elif tag == "insert":
            out += [{"type": "added", "old_text": None, "new_text": t} for t in b[j1:j2]]
        else:  # replace: pair by index, leftovers are removed / added
            olds, news = a[i1:i2], b[j1:j2]
            for k in range(min(len(olds), len(news))):
                out.append(
                    {
                        "type": "edited",
                        "old_text": olds[k],
                        "new_text": news[k],
                        "parts": _word_parts(olds[k], news[k]),
                    }
                )
            out += [{"type": "removed", "old_text": t, "new_text": None} for t in olds[len(news) :]]
            out += [{"type": "added", "old_text": None, "new_text": t} for t in news[len(olds) :]]
    return out


def _field(old: str | None, new: str | None) -> dict:
    return {"old": old, "new": new, "changed": (old or "") != (new or "")}


def build_diff(old: dict, new: dict, author: dict, meta: dict | None = None) -> dict:
    body = diff_body(old.get("body"), new.get("body"))
    for f in body:
        f["author"] = None if f["type"] == "equal" else author
        f.setdefault("parts", None)
    summary = {
        "added": sum(f["type"] == "added" for f in body),
        "removed": sum(f["type"] == "removed" for f in body),
        "edited": sum(f["type"] == "edited" for f in body),
        "unchanged": sum(f["type"] == "equal" for f in body),
    }
    title = _field(old.get("title"), new.get("title"))
    justification = _field(old.get("justification"), new.get("justification"))
    return {
        "header": {**(meta or {}), "author": author},
        "title": title,
        "justification": justification,
        "body": body,
        "summary": summary,
        "has_changes": title["changed"]
        or justification["changed"]
        or any(summary[k] for k in ("added", "removed", "edited")),
    }


def attribute_range(diff: dict, versions_in_range: list[dict]) -> dict:
    """Re-attribute fragments of a multi-step diff (base k -> n) to the version that really made them.

    versions_in_range: versions k+1..n in order, each {"author": ref, "body": str}.
    """
    sets = [(v["author"], set(split_fragments(v["body"]))) for v in versions_in_range]
    for f in diff["body"]:
        if f["type"] in ("added", "edited"):
            f["author"] = next((a for a, s in sets if f["new_text"] in s), f["author"])
        elif f["type"] == "removed":
            f["author"] = next((a for a, s in sets if f["old_text"] not in s), f["author"])
    return diff


def get_approvers(db: Session, version: EntryVersion) -> list[dict]:
    out: list[dict] = []
    rows = (
        db.query(Verification)
        .filter(Verification.version_id == version.id, Verification.action == "verify")
        .order_by(Verification.created_at, Verification.id)
        .all()
    )
    for r in rows:
        out.append(
            {
                "user": user_ref(r.verifier),
                "role": r.role,
                "action": r.action,
                "created_at": r.created_at,
                "source": "verification",
            }
        )
    if version.source_pr_id is not None:
        approvals = (
            db.query(PRApproval)
            .filter(PRApproval.pull_request_id == version.source_pr_id, PRApproval.action == "approve")
            .order_by(PRApproval.created_at, PRApproval.id)
            .all()
        )
        for r in approvals:
            out.append(
                {
                    "user": user_ref(r.approver),
                    "role": r.step,
                    "action": r.action,
                    "created_at": r.created_at,
                    "source": "pull_request",
                }
            )
    return out
