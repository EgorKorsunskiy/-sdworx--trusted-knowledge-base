from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.models import EntryVersion, PRApproval, PullRequest
from app.services.diff import attribute_range, build_diff, diff_body, split_fragments
from tests.conftest import login

A = {"id": 1, "display_name": "Employee A", "title": None}
B = {"id": 2, "display_name": "Employee B", "title": None}
C = {"id": 4, "display_name": "Senior Expert", "title": None}


def snap(title="T", body="", justification=None):
    return {"title": title, "body": body, "justification": justification}


def types(diff):
    return [f["type"] for f in diff["body"]]


# ---------- unit tests (no DB) ----------


def test_split_fragments():
    assert split_fragments("") == []
    assert split_fragments(None) == []
    assert split_fragments("One. Two!\r\n\r\n- bullet a\n- bullet b? Yes.") == [
        "One.",
        "Two!",
        "- bullet a",
        "- bullet b?",
        "Yes.",
    ]


def test_diff_added_removed_equal():
    d = build_diff(snap(body="One. Two."), snap(body="One. Two. Three."), A)
    assert types(d) == ["equal", "equal", "added"]
    assert d["summary"] == {"added": 1, "removed": 0, "edited": 0, "unchanged": 2}
    d = build_diff(snap(body="One. Two. Three."), snap(body="One. Three."), A)
    assert types(d) == ["equal", "removed", "equal"]
    assert d["body"][1]["old_text"] == "Two." and d["body"][1]["new_text"] is None


def test_diff_edited_has_word_parts():
    d = build_diff(snap(body="The rate is 20 percent."), snap(body="The rate is 21 percent."), A)
    assert types(d) == ["edited"]
    ops = [(p["op"], p["text"]) for p in d["body"][0]["parts"]]
    assert ("delete", "20") in ops and ("insert", "21") in ops
    assert ops[0] == ("equal", "The rate is")


def test_diff_unequal_replace_block():
    d = build_diff(snap(body="Old one."), snap(body="New one. Another."), A)
    assert sorted(types(d)) == ["added", "edited"]
    assert d["summary"]["edited"] == 1 and d["summary"]["added"] == 1
    assert [f["type"] for f in diff_body("A. B.", "C.")] == ["edited", "removed"]


def test_identical_snapshots():
    s = snap(body="One. Two.", justification="why")
    d = build_diff(s, dict(s), A)
    assert d["has_changes"] is False
    assert d["summary"] == {"added": 0, "removed": 0, "edited": 0, "unchanged": 2}
    assert set(types(d)) == {"equal"}
    assert not d["title"]["changed"] and not d["justification"]["changed"]


def test_title_and_justification_changes():
    d = build_diff(snap(title="Old", body="X."), snap(title="New", body="X."), A)
    assert d["title"] == {"old": "Old", "new": "New", "changed": True}
    assert d["has_changes"] is True
    d = build_diff(snap(body="X."), snap(body="X.", justification="Because"), A)
    assert d["justification"] == {"old": None, "new": "Because", "changed": True}
    d = build_diff(snap(body="X.", justification=None), snap(body="X.", justification=""), A)
    assert d["justification"]["changed"] is False
    assert d["justification"]["old"] is None


def test_attribution_and_meta():
    d = build_diff(snap(body="One. Two."), snap(body="One. Three."), B, {"public_id": "X"})
    assert d["header"] == {"public_id": "X", "author": B}
    by_type = {f["type"]: f for f in d["body"]}
    assert by_type["equal"]["author"] is None
    assert by_type["edited"]["author"] == B


def test_empty_old_snapshot():
    empty = {"title": "", "body": "", "justification": None}
    d = build_diff(empty, snap(title="Hello", body="One. Two."), A)
    assert types(d) == ["added", "added"]
    assert d["title"]["changed"] is True
    assert all(f["author"] == A for f in d["body"])


def test_attribute_range():
    v_a = {"author": A, "body": "One. Two. Four."}
    v_b = {"author": B, "body": "One. Two. Four. Three."}
    v_c = {"author": C, "body": "One. Four. Three."}
    d = build_diff(snap(body=v_a["body"]), snap(body=v_c["body"]), C)
    attribute_range(d, [v_b, v_c])
    by_type = {f["type"]: f for f in d["body"]}
    assert by_type["added"]["author"] == B  # Three. first appeared in v_b
    assert by_type["removed"]["author"] == C  # Two. first missing in v_c
    assert by_type["equal"]["author"] is None


# ---------- API tests ----------


def test_history_404_and_diff_errors(client, history_entry):
    h = login(client, 1)
    assert client.get("/entries/NOPE/history", headers=h).status_code == 404
    assert client.get("/entries/NOPE/versions/1/diff", headers=h).status_code == 404
    assert client.get(f"/entries/{history_entry}/versions/9/diff", headers=h).status_code == 404
    r = client.get(f"/entries/{history_entry}/versions/3/diff?against=0", headers=h)
    assert r.status_code == 404 and r.json()["detail"] == "Base version not found"
    assert client.get(f"/entries/{history_entry}/versions/3/diff?against=3", headers=h).status_code == 400
    assert client.get(f"/entries/{history_entry}/versions/2/diff?against=5", headers=h).status_code == 400
    assert client.get(f"/entries/{history_entry}/history").status_code == 401


def test_history_list(client, history_entry):
    r = client.get(f"/entries/{history_entry}/history", headers=login(client, 3))
    assert r.status_code == 200, r.text
    items = r.json()
    assert [i["version_number"] for i in items] == [3, 2, 1]
    assert [i["is_current"] for i in items] == [True, False, False]
    assert [i["author"]["display_name"] for i in items] == ["Senior Expert", "Employee B", "Employee A"]
    assert [i["verifier_role"] for i in items] == [None, "Team Lead", "Senior Expert"]
    assert items[1]["change_note"] == "Clarified quarterly rate and added exemption"
    assert items[1]["summary"] == {"added": 1, "removed": 0, "edited": 1, "unchanged": 2}
    assert items[0]["summary"] == {"added": 0, "removed": 1, "edited": 0, "unchanged": 3}
    assert items[2]["summary"]["added"] == 3 and items[2]["summary"]["unchanged"] == 0
    assert items[1]["approvers"][0]["user"]["display_name"] == "Team Lead"


def test_diff_v2_vs_v1(client, history_entry):
    r = client.get(f"/entries/{history_entry}/versions/2/diff", headers=login(client, 1))
    assert r.status_code == 200, r.text
    d = r.json()
    h = d["header"]
    assert h["public_id"] == history_entry
    assert (h["kind"], h["from_version"], h["to_version"]) == ("change", 1, 2)
    assert h["author"]["display_name"] == "Employee B"
    assert h["change_note"] == "Clarified quarterly rate and added exemption"
    assert h["created_at"]
    assert [(a["user"]["display_name"], a["action"], a["role"]) for a in h["approvers"]] == [
        ("Team Lead", "verify", "Team Lead")
    ]
    assert h["approvers"][0]["source"] == "verification"
    for f in d["body"]:
        if f["type"] == "equal":
            assert f["author"] is None
        else:
            assert f["author"]["display_name"] == "Employee B"
    assert sorted(f["type"] for f in d["body"]) == ["added", "edited", "equal", "equal"]
    assert d["has_changes"] and not d["title"]["changed"]


def test_diff_v3_title_change_unverified(client, history_entry):
    d = client.get(f"/entries/{history_entry}/versions/3/diff", headers=login(client, 1)).json()
    assert d["title"]["changed"] and d["title"]["new"].endswith("(2026)")
    assert d["justification"]["changed"]
    assert d["header"]["approvers"] == []
    assert d["header"]["author"]["display_name"] == "Senior Expert"
    removed = [f for f in d["body"] if f["type"] == "removed"]
    assert len(removed) == 1 and removed[0]["author"]["display_name"] == "Senior Expert"


def test_diff_v1_created(client, history_entry):
    d = client.get(f"/entries/{history_entry}/versions/1/diff", headers=login(client, 1)).json()
    h = d["header"]
    assert h["kind"] == "created" and h["from_version"] is None and h["to_version"] == 1
    assert h["author"]["display_name"] == "Employee A"
    assert [a["user"]["display_name"] for a in h["approvers"]] == ["Senior Expert"]
    assert {f["type"] for f in d["body"]} == {"added"}
    assert d["title"]["changed"]


def test_diff_against_older_version_attribution(client, history_entry):
    d = client.get(
        f"/entries/{history_entry}/versions/3/diff?against=1", headers=login(client, 1)
    ).json()
    assert d["header"]["from_version"] == 1 and d["header"]["to_version"] == 3
    # every change in 1 -> 3 first appeared in v2 (the new sentences) so it is attributed to Employee B
    for f in d["body"]:
        if f["type"] == "equal":
            assert f["author"] is None
        else:
            assert f["author"]["display_name"] == "Employee B"
    assert {f["type"] for f in d["body"]} >= {"edited", "added"}


def test_diff_approvers_from_pull_request(client, history_entry, db_session):
    v3 = (
        db_session.query(EntryVersion)
        .filter(EntryVersion.version_number == 3)
        .order_by(EntryVersion.id.desc())
        .first()
    )
    pr = PullRequest(
        entry_id=v3.entry_id,
        author_id=3,
        proposed_title="t",
        proposed_body="b",
    )
    db_session.add(pr)
    db_session.flush()
    now = datetime.utcnow()
    db_session.add(PRApproval(pull_request_id=pr.id, approver_id=2, step="author", action="approve", created_at=now))
    db_session.add(
        PRApproval(pull_request_id=pr.id, approver_id=4, step="verifier", action="approve", created_at=now + timedelta(hours=1))
    )
    db_session.add(PRApproval(pull_request_id=pr.id, approver_id=5, step="verifier", action="reject"))
    v3.source_pr_id = pr.id
    pr_id = pr.id
    db_session.commit()
    db_session.close()
    d = client.get(f"/entries/{history_entry}/versions/3/diff", headers=login(client, 1)).json()
    approvers = d["header"]["approvers"]
    assert [(a["user"]["display_name"], a["role"], a["source"]) for a in approvers] == [
        ("Employee B", "author", "pull_request"),
        ("Senior Expert", "verifier", "pull_request"),
    ]
    assert d["header"]["pull_request_id"] == pr_id


def test_patch_in_place_keeps_one_version(client):
    h = login(client, 1)
    r = client.patch("/entries/PP-BE-FRE-00001", headers=h, json={"body": "Changed body text."})
    assert r.status_code == 200, r.text
    items = client.get("/entries/PP-BE-FRE-00001/history", headers=h).json()
    assert len(items) == 1
    assert items[0]["change_note"] == "Updated draft"
    d = client.get("/entries/PP-BE-FRE-00001/versions/1/diff", headers=h).json()
    assert d["header"]["kind"] == "created"


def test_seed_history_demo_idempotent(client):
    from app import seeds as seeds_mod

    seeds_mod.seed_history_demo()
    seeds_mod.seed_history_demo()
    from sqlalchemy.orm import Session

    from app.models import Entry, Tag

    with Session(seeds_mod.engine) as db:
        entries = db.query(Entry).join(Entry.tags).filter(Tag.name == "history-demo").all()
        assert len(entries) == 1
        assert len(entries[0].versions) == 3


def test_ensure_columns_adds_source_pr_id():
    from app.database import _ensure_columns

    eng = create_engine("sqlite://", poolclass=StaticPool)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE entry_versions (id INTEGER PRIMARY KEY)"))
    for _ in range(2):
        _ensure_columns(eng)
    assert "source_pr_id" in {c["name"] for c in inspect(eng).get_columns("entry_versions")}
