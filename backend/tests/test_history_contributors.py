from app.models import User
from app.services.reputation import reputation_value
from tests.conftest import login

PID = "PP-BE-FRE-00001"
VOTE = {"used_at": "2026-01-01", "where_ref": "x", "is_correct": True}


def _get(client, uid, pid, **params):
    return client.get(f"/entries/{pid}/contributors", params=params, headers=login(client, uid))


def test_requires_auth_and_validation(client, history_entry):
    assert client.get(f"/entries/{history_entry}/contributors").status_code == 401
    assert _get(client, 3, "NOPE-1").status_code == 404
    r = _get(client, 3, history_entry, version=99)
    assert r.status_code == 404 and r.json()["detail"] == "Version not found"
    assert _get(client, 3, history_entry, version=0).status_code == 422


def test_blame_shape_for_history_entry(client, history_entry):
    d = _get(client, 3, history_entry).json()
    assert d["version_number"] == d["current_version_number"] == 3
    frags = d["fragments"]
    assert len(frags) == 3
    got = [(f["index"], f["contributor_ids"], f["introduced_in_version"], f["last_edited_in_version"]) for f in frags]
    assert got == [(0, [1, 2], 1, 2), (1, [1], 1, 1), (2, [2], 2, 2)]

    by = {c["user"]["id"]: c for c in d["contributors"]}
    assert set(by) == {1, 2}  # user 4 owns no current line
    assert by[1]["fragment_indexes"] == [0, 1] and by[1]["fragment_count"] == 2
    assert by[2]["fragment_indexes"] == [0, 2] and by[2]["fragment_count"] == 2
    for c in by.values():
        u = c["user"]
        assert u["role_badge"] and u["email"] and isinstance(u["reputation"], int)
    assert by[1]["user"]["role_badge"] == "Employee"
    assert 2 not in frags[1]["contributor_ids"] and 1 not in frags[2]["contributor_ids"]


def test_version_param_and_reconstruction(client, history_entry):
    d = _get(client, 3, history_entry, version=1).json()
    assert d["version_number"] == 1 and d["current_version_number"] == 3
    assert len(d["fragments"]) == 3
    assert all(f["contributor_ids"] == [1] for f in d["fragments"])
    assert [c["user"]["id"] for c in d["contributors"]] == [1]

    cur = _get(client, 3, history_entry).json()
    body = client.get(f"/entries/{history_entry}", headers=login(client, 3)).json()["current_version"]["body"]
    assert "".join(f["separator_before"] + f["text"] for f in cur["fragments"]) == body


def test_pr_merge_blame(client):
    cur = client.get(f"/entries/{PID}", headers=login(client, 1)).json()["current_version"]
    s1, s3 = "First fact.", "Third fact."
    r = client.patch(
        f"/entries/{PID}", json={"body": f"{s1} Second fact.\n{s3}"}, headers=login(client, 1)
    )
    assert r.status_code == 200, r.text
    pr = client.post(
        f"/entries/{PID}/pull-requests",
        json={
            "proposed_title": cur["title"],
            "proposed_body": f"{s1} Second fact, improved.\n{s3}",
            "proposed_justification": cur["justification"],
            "change_note": "Improve second",
            "basis": "responsible",
        },
        headers=login(client, 2),
    )
    assert pr.status_code == 201, pr.text
    # The entry author's approval is the only one a PR needs.
    r = client.post(f"/pull-requests/{pr.json()['id']}/approve", headers=login(client, 1))
    assert r.status_code == 200, r.text

    d = _get(client, 3, PID).json()
    assert [f["text"] for f in d["fragments"]] == [s1, "Second fact, improved.", s3]
    assert [f["contributor_ids"] for f in d["fragments"]] == [[1], [1, 2], [1]]
    ids = {c["user"]["id"] for c in d["contributors"]}
    assert ids == {1, 2}  # senior expert (4) and user 3 own no line
    assert d["viewer_is_contributor"] is False
    assert _get(client, 2, PID).json()["viewer_is_contributor"] is True


def test_contributors_cannot_vote_and_reputation(client, db_session, history_entry):
    url = f"/entries/{history_entry}/votes"
    for uid in (1, 2, 4):
        r = client.post(url, json=VOTE, headers=login(client, uid))
        assert r.status_code == 403, (uid, r.text)
        assert _get(client, uid, history_entry).json()["viewer_is_contributor"] is True
    assert _get(client, 3, history_entry).json()["viewer_is_contributor"] is False

    points = reputation_value(db_session, "reputation_vote")
    assert points > 0
    before = {u.id: u.reputation for u in db_session.query(User).all()}
    db_session.close()

    assert client.post(url, json=VOTE, headers=login(client, 3)).status_code == 200
    db_session.expire_all()
    after = {u.id: u.reputation for u in db_session.query(User).all()}
    for uid in (1, 2, 4):
        assert after[uid] == before[uid] + points, uid
    for uid in (3, 5, 6, 7):
        assert after[uid] == before[uid], uid
    db_session.close()

    assert client.post(url, json=VOTE, headers=login(client, 3)).status_code == 409
