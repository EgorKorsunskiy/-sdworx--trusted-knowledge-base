from app.models import (
    Entry,
    EntryVersion,
    OutdatedResolution,
    PRApproval,
    PullRequest,
    Team,
    TeamMembership,
    User,
    UserRole,
)
from tests.conftest import login

PID = "PP-BE-FRE-00001"
SENIOR, TEAM_LEAD, MANAGER, ADMIN = 4, 5, 6, 7
A, B, C = 1, 2, 3


def _open(client, hdr, **over):
    body = {
        "proposed_title": "Zebrafoo payroll rules",
        "proposed_body": "First sentence is new. Second sentence is also new.",
        "proposed_justification": "Because the law changed.",
        "change_note": "Update after law change",
    }
    body.update(over)
    return client.post(f"/entries/{PID}/pull-requests", json=body, headers=hdr)


def _hdr(client, uid):
    return login(client, uid)


def _approve(client, uid, pr_id, **kw):
    return client.post(f"/pull-requests/{pr_id}/approve", headers=_hdr(client, uid), **kw)


def _reject(client, uid, pr_id, reason="Not accurate"):
    return client.post(f"/pull-requests/{pr_id}/reject", json={"reason": reason}, headers=_hdr(client, uid))


def _merge_new(client, **over):
    """B opens, A (the entry author) approves: that is enough to merge. Returns the PR id."""
    pr = _open(client, _hdr(client, B), **over).json()
    r = _approve(client, A, pr["id"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "merged"
    return pr["id"]


def _notifs(client, uid, event=None):
    rows = client.get("/notifications", headers=_hdr(client, uid)).json()
    return [n for n in rows if event is None or n["event_type"] == event]


def _pending_ids(client, uid):
    r = client.get("/pull-requests/pending", headers=_hdr(client, uid))
    assert r.status_code == 200, r.text
    return [(p["id"], p["step"]) for p in r.json()]


# (1) open
def test_open_and_validation(client):
    hdr = _hdr(client, B)
    r = _open(client, hdr)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "open" and d["base_version_number"] == 1
    assert d["entry"]["public_id"] == PID and d["next_step"] == "author"
    assert d["can_approve_as_author"] is False and d["can_reject"] is False  # B is the PR author

    cur = client.get(f"/entries/{PID}", headers=hdr).json()["current_version"]
    assert _open(client, hdr, proposed_title=cur["title"], proposed_body=cur["body"],
                 proposed_justification=cur["justification"]).status_code == 422
    assert _open(client, hdr, proposed_title="  ", proposed_body="", proposed_justification=None).status_code == 422
    bad = {"proposed_title": "x"}
    assert client.post(f"/entries/{PID}/pull-requests", json=bad, headers=hdr).status_code == 422
    assert _open(client, hdr, change_note="   ").status_code == 422
    assert _open(client, hdr, proposed_body="x" * 20001).status_code == 422
    assert client.post("/entries/NOPE/pull-requests", json={"change_note": "n", "proposed_title": "t"},
                       headers=hdr).status_code == 404


# (2) lifecycle: the entry author's approval merges the PR
def test_full_lifecycle(client, db_session):
    before = client.get(f"/entries/{PID}", headers=_hdr(client, A)).json()["updated_at"]
    pr_id = _merge_new(client)

    hdr = _hdr(client, A)
    found = [e for e in client.get("/search", headers=hdr).json() if e["public_id"] == PID]
    assert len(found) == 1 and found[0]["current_version"]["title"] == "Zebrafoo payroll rules"

    e = client.get(f"/entries/{PID}", headers=hdr).json()
    cv = e["current_version"]
    # No verifier was involved: the merged version is an ordinary Unverified one.
    assert cv["version_number"] == 2 and cv["status"] == "Unverified"
    assert cv["edited_by"]["id"] == B and cv["change_note"] == "Update after law change"
    assert e["updated_at"] != before
    assert client.get(f"/entries/{PID}/versions/1/diff", headers=hdr).status_code == 200

    pr = client.get(f"/pull-requests/{pr_id}", headers=hdr).json()
    assert pr["status"] == "merged" and pr["merged_version_number"] == 2 and pr["resolved_at"]
    assert pr["next_step"] is None and pr["waiting_on"] == []

    v2 = db_session.query(EntryVersion).filter_by(version_number=2).one()
    assert v2.source_pr_id == pr_id
    assert db_session.query(Entry).count() == 1
    db_session.close()

    hist = client.get(f"/entries/{PID}/history", headers=hdr).json()
    assert [h["version_number"] for h in hist] == [2, 1]
    assert [(a["role"], a["source"], a["user"]["id"]) for a in hist[0]["approvers"]] == [
        ("author", "pull_request", A),
    ]
    diff = client.get(f"/entries/{PID}/versions/2/diff", headers=hdr).json()
    assert [(a["role"], a["source"]) for a in diff["header"]["approvers"]] == [("author", "pull_request")]
    changed = [f for f in diff["body"] if f["type"] != "equal"]
    assert changed and all(f["author"]["id"] == B for f in changed)

    # The merged version then goes through normal verification (it shows up for verifiers in scope).
    pending = client.get("/approvals/pending", headers=_hdr(client, SENIOR)).json()
    # only the current version is queued; the superseded Unverified v1 is not
    assert [(p["entry"]["public_id"], p["version"]["version_number"]) for p in pending] == [(PID, 2)]
    old = client.get(f"/entries/{PID}/history", headers=hdr).json()[-1]["version_id"]
    assert client.post(f"/approvals/{old}/verify", headers=_hdr(client, SENIOR)).status_code == 409
    v = client.post(f"/approvals/{pending[0]['version']['id']}/verify", headers=_hdr(client, SENIOR))
    assert v.status_code == 200
    assert client.get(f"/entries/{PID}", headers=hdr).json()["current_version"]["status"] == "Verified"


# (3) order: only the entry author approves
def test_only_the_entry_author_approves(client):
    pr = _open(client, _hdr(client, B)).json()["id"]
    r = _approve(client, SENIOR, pr)
    assert r.status_code == 409 and "entry author" in r.json()["detail"]
    assert _reject(client, SENIOR, pr).status_code == 409
    assert _approve(client, A, pr).status_code == 200
    for uid in (A, SENIOR, B):
        assert _approve(client, uid, pr).status_code == 409  # already merged
    assert _approve(client, A, 9999).status_code == 404


# (4) scope
def test_scope(client, db_session):
    team = Team(name="Other team", department="Other")
    db_session.add(team)
    db_session.flush()
    other = User(email="other.lead@example.com", display_name="Other Lead", department="Other")
    db_session.add(other)
    db_session.flush()
    db_session.add(TeamMembership(user_id=other.id, team_id=team.id, is_primary=True))
    db_session.add(UserRole(user_id=other.id, role="team_lead"))
    db_session.commit()
    other_id = other.id
    db_session.close()

    pr = _open(client, _hdr(client, B)).json()["id"]
    assert _approve(client, B, pr).status_code == 403  # own PR
    assert _reject(client, B, pr).status_code == 403
    for uid in (C, ADMIN, other_id):
        assert _approve(client, uid, pr).status_code == 403  # no role on this PR
        assert _reject(client, uid, pr).status_code == 403
    for uid in (SENIOR, TEAM_LEAD, MANAGER):
        assert _approve(client, uid, pr).status_code == 409  # verifiers wait for the author
    assert _approve(client, A, pr).status_code == 200


# (5) reject
def test_reject_by_author(client, db_session):
    pr = _open(client, _hdr(client, B)).json()["id"]
    assert _reject(client, A, pr, "").status_code == 422
    assert _reject(client, A, pr, "   ").status_code == 422
    assert client.post(f"/pull-requests/{pr}/reject", json={}, headers=_hdr(client, A)).status_code == 422
    r = _reject(client, A, pr, "Wrong rule")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "rejected" and d["rejection_reason"] == "Wrong rule" and d["resolved_at"]
    n = _notifs(client, B, "pr_rejected")
    assert len(n) == 1 and "Wrong rule" in n[0]["body"] and n[0]["link"] == f"/pull-requests/{pr}"
    assert db_session.query(EntryVersion).count() == 1
    assert _reject(client, A, pr).status_code == 409
    assert _approve(client, A, pr).status_code == 409


def test_cannot_reject_after_merge(client):
    pr = _merge_new(client)
    assert _reject(client, A, pr).status_code == 409


# (6) stale
def test_stale_base(client):
    hb = _hdr(client, B)
    first = _open(client, hb).json()["id"]
    second = _open(client, hb, proposed_title="Other title").json()["id"]
    assert _approve(client, A, first).status_code == 200  # now current is v2
    r = _approve(client, A, second)
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    d = client.get(f"/pull-requests/{second}", headers=_hdr(client, A)).json()
    assert d["is_stale"] is True and d["can_approve_as_author"] is False and d["can_reject"] is True
    assert _reject(client, A, second).status_code == 200
    # the diff stays based on v1
    diff = client.get(f"/pull-requests/{second}/diff", headers=hb).json()
    assert diff["header"]["from_version"] == 1


# (7) author inactive: a verifier in scope approves in their place
def _deactivate(db_session, uid=1):
    db_session.query(User).filter_by(id=uid).one().is_active = False
    db_session.commit()
    db_session.close()


def test_inactive_author_at_open(client, db_session):
    _deactivate(db_session)
    d = _open(client, _hdr(client, B)).json()
    assert d["status"] == "open" and d["next_step"] == "verifier"
    assert d["approvals"] == []
    assert {p["id"] for p in d["waiting_on"]} == {SENIOR, TEAM_LEAD, MANAGER}
    assert len(_notifs(client, SENIOR, "pr_opened")) == 1
    assert _pending_ids(client, SENIOR) == [(d["id"], "verifier")]
    r = _approve(client, SENIOR, d["id"])
    assert r.status_code == 200 and r.json()["status"] == "merged"
    assert [(a["step"], a["action"]) for a in r.json()["approvals"]] == [("author", "skip"), ("verifier", "approve")]
    ap = client.get(f"/entries/{PID}/history", headers=_hdr(client, B)).json()[0]["approvers"]
    assert [a["role"] for a in ap] == ["verifier"]


def test_inactive_author_after_open(client, db_session):
    pr = _open(client, _hdr(client, B)).json()["id"]
    _deactivate(db_session)
    r = _approve(client, SENIOR, pr)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "merged"
    assert [(a["step"], a["action"]) for a in d["approvals"]] == [("author", "skip"), ("verifier", "approve")]
    ap = client.get(f"/entries/{PID}/history", headers=_hdr(client, B)).json()[0]["approvers"]
    assert [a["role"] for a in ap] == ["verifier"]


# (8) self PR: the author's own approval is implicit, so it merges right away
def test_self_pr(client, db_session):
    rep = db_session.query(User).filter_by(id=A).one().reputation
    db_session.close()
    d = _open(client, _hdr(client, A)).json()
    assert d["status"] == "merged" and d["merged_version_number"] == 2
    assert len(d["approvals"]) == 1
    a = d["approvals"][0]
    assert a["step"] == "author" and a["action"] == "approve" and a["comment"].startswith("Automatic")
    cv = client.get(f"/entries/{PID}", headers=_hdr(client, A)).json()["current_version"]
    assert cv["version_number"] == 2 and cv["status"] == "Unverified" and cv["edited_by"]["id"] == A
    for uid in (SENIOR, TEAM_LEAD, MANAGER):
        assert len(_notifs(client, uid, "new_version_in_scope")) == 1
    assert _approve(client, A, d["id"]).status_code == 409  # already merged
    assert db_session.query(User).filter_by(id=A).one().reputation == rep


# (9) notifications
def test_notifications(client):
    pr = _open(client, _hdr(client, B)).json()["id"]
    opened = _notifs(client, A, "pr_opened")
    assert len(opened) == 1 and opened[0]["link"] == f"/pull-requests/{pr}"
    for uid in (SENIOR, TEAM_LEAD, MANAGER):
        assert _notifs(client, uid) == []  # verifiers only hear about it once there is a version to verify

    assert _approve(client, A, pr).status_code == 200
    merged = _notifs(client, B, "pr_merged")
    assert len(merged) == 1 and merged[0]["link"] == f"/entries/{PID}"
    assert _notifs(client, A, "pr_merged") == []  # A did the merging themselves
    for uid in (SENIOR, TEAM_LEAD, MANAGER):
        n = _notifs(client, uid, "new_version_in_scope")
        assert len(n) == 1 and n[0]["link"] == f"/entries/{PID}"
    assert _notifs(client, C, "pr_merged") == [] and _notifs(client, C, "new_version_in_scope") == []
    for uid in (A, B, C, SENIOR, TEAM_LEAD, MANAGER):
        assert _notifs(client, uid, "pr_author_approved") == []


# (10) reputation
def test_reputation(client, db_session):
    def rep(uid):
        db_session.expire_all()
        v = db_session.query(User).filter_by(id=uid).one().reputation
        db_session.close()
        return v

    start = rep(B)
    _merge_new(client)
    assert rep(B) == start + 5
    r = client.put("/admin/settings/reputation_pr_merged", params={"value": "9"}, headers=_hdr(client, ADMIN))
    assert r.status_code == 200, r.text
    hb = _hdr(client, B)
    pr = _open(client, hb, proposed_title="Another title").json()["id"]
    assert _approve(client, A, pr).status_code == 200
    assert rep(B) == start + 5 + 9


# (11) outdated
def test_merge_resolves_outdated(client, db_session):
    v1 = db_session.query(EntryVersion).filter_by(version_number=1).one()
    v1.status = "Stale"
    v1_id = v1.id
    db_session.commit()
    db_session.close()
    _merge_new(client)
    e = client.get(f"/entries/{PID}", headers=_hdr(client, A)).json()
    assert e["current_version"]["status"] == "Unverified" and e["current_version"]["version_number"] == 2
    rows = db_session.query(OutdatedResolution).filter_by(version_id=v1_id).all()
    assert [r.action for r in rows] == ["merged_pr"]


# (12) pending queue: only the entry author sees it (verifiers only if the author is gone)
def test_pending_queue(client):
    pr = _open(client, _hdr(client, B)).json()["id"]
    assert _pending_ids(client, A) == [(pr, "author")]
    for uid in (SENIOR, TEAM_LEAD, MANAGER, B, C, ADMIN):
        assert _pending_ids(client, uid) == []
    assert _approve(client, A, pr).status_code == 200
    for uid in (A, B, C, SENIOR, TEAM_LEAD, MANAGER, ADMIN):
        assert _pending_ids(client, uid) == []


# (13) diff endpoint and flags
def test_diff_and_flags(client):
    pr = _open(client, _hdr(client, B)).json()["id"]
    d = client.get(f"/pull-requests/{pr}/diff", headers=_hdr(client, C)).json()
    h = d["header"]
    assert h["kind"] == "proposal" and h["from_version"] == 1 and h["to_version"] is None
    assert h["author"]["id"] == B and h["pull_request_id"] == pr
    assert h["change_note"] == "Update after law change" and h["status"] == "open"
    assert d["title"]["changed"] is True
    changed = [f for f in d["body"] if f["type"] != "equal"]
    assert changed and all(f["author"]["id"] == B for f in changed)

    assert client.get(f"/pull-requests/{pr}", headers=_hdr(client, A)).json()["can_approve_as_author"] is True
    for uid in (B, C, SENIOR):
        assert client.get(f"/pull-requests/{pr}", headers=_hdr(client, uid)).json()["can_approve_as_author"] is False
    assert client.get(f"/pull-requests/{pr}", headers=_hdr(client, B)).json()["can_reject"] is False
    assert client.get(f"/pull-requests/{pr}", headers=_hdr(client, A)).json()["can_reject"] is True
    assert client.get("/pull-requests/9999/diff", headers=_hdr(client, A)).status_code == 404


# (14) lists
def test_lists(client):
    hb = _hdr(client, B)
    first = _open(client, hb).json()["id"]
    second = _open(client, hb, proposed_title="Second").json()["id"]
    assert _reject(client, A, first).status_code == 200
    allp = client.get(f"/entries/{PID}/pull-requests", headers=hb).json()
    assert [p["id"] for p in allp] == [second, first]
    openp = client.get(f"/entries/{PID}/pull-requests", params={"open_only": "true"}, headers=hb).json()
    assert [p["id"] for p in openp] == [second]
    mine = client.get("/me/contributions", headers=hb).json()["pull_requests"]
    row = next(p for p in mine if p["id"] == first)
    assert row["status"] == "rejected" and row["entry_public_id"] == PID and row["change_note"]
    assert row["entry_title"]


def test_waiting_on_is_the_entry_author(client):
    pr = _open(client, _hdr(client, B)).json()
    detail = client.get(f"/pull-requests/{pr['id']}", headers=_hdr(client, B)).json()
    assert detail["next_step"] == "author"
    assert [p["id"] for p in detail["waiting_on"]] == [A]

    assert _approve(client, A, pr["id"]).status_code == 200
    detail = client.get(f"/pull-requests/{pr['id']}", headers=_hdr(client, B)).json()
    assert detail["status"] == "merged" and detail["next_step"] is None and detail["waiting_on"] == []
    entry = client.get(f"/entries/{PID}", headers=_hdr(client, B)).json()
    assert entry["current_version"]["version_number"] == 2


def test_entry_nobody_can_verify_still_merges_on_author_approval(client):
    # Admin's entry is in the "Platform" department with no team: no verifier is in scope for it,
    # but a PR no longer needs one. The new version is simply Unverified like the original.
    made = client.post(
        "/entries",
        headers=_hdr(client, ADMIN),
        json={"title": "Platform runbook", "body": "Restart the thing.", "category_id": 1, "country": "BE", "scope": "country"},
    ).json()
    pid = made["public_id"]
    pr = client.post(
        f"/entries/{pid}/pull-requests",
        headers=_hdr(client, B),
        json={"proposed_body": "Restart the thing twice.", "change_note": "clarify"},
    ).json()
    r = _approve(client, ADMIN, pr["id"])
    assert r.status_code == 200 and r.json()["status"] == "merged"
    cv = client.get(f"/entries/{pid}", headers=_hdr(client, B)).json()["current_version"]
    assert cv["version_number"] == 2 and cv["status"] == "Unverified" and cv["body"] == "Restart the thing twice."


def test_legacy_author_approved_prs_are_finished_at_startup(client, db_session):
    """PRs the old two-step rule left 'author_approved' are merged (or reopened if stale)."""
    from app import seeds

    ok = PullRequest(entry_id=1, author_id=B, status="author_approved", title="old", proposed_title="Legacy title",
                     change_note="legacy", base_version_number=1)
    stale = PullRequest(entry_id=1, author_id=C, status="author_approved", title="old2", proposed_title="Other",
                        change_note="legacy2", base_version_number=1)
    db_session.add_all([ok, stale])
    db_session.flush()
    db_session.add(PRApproval(pull_request_id=ok.id, approver_id=A, step="author", action="approve"))
    db_session.add(PRApproval(pull_request_id=stale.id, approver_id=A, step="author", action="approve"))
    ok_id, stale_id = ok.id, stale.id
    db_session.commit()
    db_session.close()

    seeds.finish_legacy_pull_requests()
    seeds.finish_legacy_pull_requests()  # idempotent

    ok_pr = client.get(f"/pull-requests/{ok_id}", headers=_hdr(client, B)).json()
    stale_pr = client.get(f"/pull-requests/{stale_id}", headers=_hdr(client, B)).json()
    assert ok_pr["status"] == "merged" and ok_pr["merged_version_number"] == 2
    assert stale_pr["status"] == "open" and stale_pr["is_stale"] is True
    cv = client.get(f"/entries/{PID}", headers=_hdr(client, B)).json()["current_version"]
    assert cv["version_number"] == 2 and cv["title"] == "Legacy title" and cv["status"] == "Unverified"


def test_requires_auth(client):
    assert client.get("/pull-requests/pending").status_code == 401
    assert client.post(f"/entries/{PID}/pull-requests", json={"change_note": "x"}).status_code == 401
