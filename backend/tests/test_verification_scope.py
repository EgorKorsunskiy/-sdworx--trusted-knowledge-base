"""Who can verify what, including the fallback for entries nobody else is in scope for."""

from tests.conftest import login

SENIOR, TEAM_LEAD, MANAGER, ADMIN = 4, 5, 6, 7
A = 1


def _create(client, uid, title="Some new rule"):
    r = client.post(
        "/entries",
        headers=login(client, uid),
        json={"title": title, "body": "A rule that needs checking.", "category_id": 1, "country": "BE", "scope": "country", "basis": "responsible"},
    )
    assert r.status_code == 201, r.text
    return r.json()["public_id"]


def _pending(client, uid):
    r = client.get("/approvals/pending", headers=login(client, uid))
    assert r.status_code == 200, r.text
    return {p["entry"]["public_id"]: p["version"]["id"] for p in r.json()}


def _notifs(client, uid, event):
    rows = client.get("/notifications", headers=login(client, uid)).json()
    return [n for n in rows if n["event_type"] == event]


def test_scoped_entry_is_only_for_its_own_verifiers(client):
    pid = _create(client, A)  # Employee A: department Payroll, team 1
    for uid in (SENIOR, TEAM_LEAD, MANAGER):
        assert pid in _pending(client, uid)
    # Admin is only a fallback verifier: not here, because verifiers are in scope.
    assert pid not in _pending(client, ADMIN)
    vid = _pending(client, SENIOR)[pid]
    assert client.post(f"/approvals/{vid}/verify", headers=login(client, ADMIN)).status_code == 403


def test_manager_can_verify_an_entry_nobody_else_can(client):
    # Admin's entry: department "Platform", no team, no senior expert mapped to it.
    pid = _create(client, ADMIN)
    pending = _pending(client, MANAGER)
    assert pid in pending
    assert pid not in _pending(client, SENIOR) and pid not in _pending(client, TEAM_LEAD)
    assert pid not in _pending(client, ADMIN)  # never your own entry

    r = client.post(f"/approvals/{pending[pid]}/verify", headers=login(client, MANAGER))
    assert r.status_code == 200 and r.json()["role"] == "Manager"
    assert client.get(f"/entries/{pid}", headers=login(client, A)).json()["current_version"]["status"] == "Verified"


def test_senior_expert_entry_falls_back_to_managers_and_admins(client):
    # The Senior Expert's only team is "Payroll Experts" and they are its only lead: nobody else in scope.
    pid = _create(client, SENIOR)
    assert pid in _pending(client, MANAGER) and pid in _pending(client, ADMIN)
    assert pid not in _pending(client, TEAM_LEAD) and pid not in _pending(client, SENIOR)


def test_fallback_stops_once_someone_is_in_scope(client):
    pid = _create(client, ADMIN)
    assert pid in _pending(client, MANAGER)
    r = client.post("/admin/verifier-mappings", params={"user_id": SENIOR, "department": "Platform"},
                    headers=login(client, ADMIN))
    assert r.status_code == 200, r.text
    assert pid in _pending(client, SENIOR)  # mapped senior expert is now in scope
    assert pid not in _pending(client, MANAGER)  # so the manager fallback no longer applies
    vid = _pending(client, SENIOR)[pid]
    assert client.post(f"/approvals/{vid}/verify", headers=login(client, MANAGER)).status_code == 403


def test_verifiers_are_told_about_a_new_entry(client):
    pid = _create(client, A)
    for uid in (SENIOR, TEAM_LEAD, MANAGER):
        n = _notifs(client, uid, "new_entry")
        assert len(n) == 1 and n[0]["link"] == f"/entries/{pid}"
    assert _notifs(client, A, "new_entry") == [] and _notifs(client, ADMIN, "new_entry") == []

    # Fallback entry: the managers (and admins) hear about it instead.
    admin_pid = _create(client, ADMIN)
    assert {n["link"] for n in _notifs(client, MANAGER, "new_entry")} == {f"/entries/{pid}", f"/entries/{admin_pid}"}
    assert _notifs(client, TEAM_LEAD, "new_entry")[0]["link"] == f"/entries/{pid}" and len(_notifs(client, TEAM_LEAD, "new_entry")) == 1
    assert _notifs(client, ADMIN, "new_entry") == []


def test_who_to_ask_lists_the_fallback_verifiers(client):
    pid = _create(client, ADMIN)
    ask = client.get(f"/entries/{pid}", headers=login(client, A)).json()["who_to_ask"]
    assert [p["id"] for p in ask] == [ADMIN, MANAGER]
