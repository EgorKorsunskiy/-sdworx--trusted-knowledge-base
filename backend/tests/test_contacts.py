from sqlalchemy import select

from app.models import EntryContactChange, EntryVersion
from tests.conftest import login

A, B, C, SENIOR, TEAM_LEAD, MANAGER, ADMIN = 1, 2, 3, 4, 5, 6, 7
PID = "PP-BE-FRE-00001"  # seeded; author A


def _create(client, uid, title="Cut-off rule", **extra):
    body = {"title": title, "body": "A rule about cut-off dates.", "category_id": 1, "country": "BE",
            "scope": "country", "basis": "responsible"}
    body.update(extra)
    return client.post("/entries", headers=login(client, uid), json=body)


def _detail(client, uid, pid):
    r = client.get(f"/entries/{pid}", headers=login(client, uid))
    assert r.status_code == 200, r.text
    return r.json()


# --- adding an entry (FR-K1) -------------------------------------------------------------------------


def test_basis_is_required_to_add_an_entry(client):
    r = client.post("/entries", headers=login(client, A), json={
        "title": "t", "body": "b", "category_id": 1, "country": "BE", "scope": "country"})
    assert r.status_code == 422
    assert _create(client, A, basis="nonsense").status_code == 422


def test_relayed_needs_a_source(client):
    assert _create(client, A, basis="relayed").status_code == 422
    assert _create(client, A, basis="relayed", basis_source="   ").status_code == 422
    r = _create(client, A, basis="relayed", basis_source="Payroll newsletter, September 2026")
    assert r.status_code == 201
    mine = _detail(client, A, r.json()["public_id"])["my_contact"]
    assert mine["basis"] == "relayed" and mine["source"] == "Payroll newsletter, September 2026"


def test_responsible_drops_any_source(client):
    pid = _create(client, A, basis="responsible", basis_source="ignored").json()["public_id"]
    assert _detail(client, A, pid)["my_contact"]["source"] is None


# --- the Contacts block (FR-K3, FR-K4, FR-K5) -----------------------------------------------------------


def test_contacts_block_lists_author_with_details(client):
    d = _detail(client, B, _create(client, A).json()["public_id"])
    assert [c["role"] for c in d["contacts"]] == ["author"]
    c = d["contacts"][0]
    assert c["basis"] == "responsible" and c["user"]["display_name"] == "Employee A"
    assert c["user"]["title"] and c["user"]["department"] == "Payroll" and "reputation" in c
    assert d["no_responsible_contact"] is False and d["has_responsible_contact"] is True


def test_seeded_entries_have_their_author_as_responsible_contact(client):
    d = _detail(client, B, PID)
    assert d["contacts"][0]["user"]["id"] == A and d["contacts"][0]["basis"] == "responsible"


def test_relayed_only_entry_shows_no_responsible_contact(client):
    pid = _create(client, A, basis="relayed", basis_source="Handbook").json()["public_id"]
    d = _detail(client, B, pid)
    assert d["no_responsible_contact"] is True and d["has_responsible_contact"] is False
    assert d["who_to_ask"]  # the verifiers in scope are still listed (FR-V6, FR-K5)


def test_departed_people_are_not_shown_as_contacts(client, db_session):
    from app.models import User

    pid = _create(client, A).json()["public_id"]
    db_session.get(User, A).is_active = False
    db_session.commit()
    d = _detail(client, B, pid)
    assert d["contacts"] == [] and d["no_responsible_contact"] is True


def test_responsible_contacts_come_first(client):
    # B merges a PR as Relayed, then A (author) is switched to Relayed and B to Responsible
    pid = _create(client, A).json()["public_id"]
    pr = client.post(f"/entries/{pid}/pull-requests", headers=login(client, B), json={
        "proposed_body": "A rule about cut-off dates. Plus a new sentence.", "change_note": "more",
        "basis": "relayed", "basis_source": "Colleague Karen"}).json()
    assert client.post(f"/pull-requests/{pr['id']}/approve", headers=login(client, A)).status_code == 200
    assert [c["user"]["id"] for c in _detail(client, C, pid)["contacts"]] == [A, B]  # author is responsible

    client.put(f"/entries/{pid}/my-basis", headers=login(client, A), json={"basis": "relayed", "source": "Law"})
    client.put(f"/entries/{pid}/my-basis", headers=login(client, B), json={"basis": "responsible"})
    contacts = _detail(client, C, pid)["contacts"]
    assert [c["user"]["id"] for c in contacts] == [B, A]
    assert [c["basis"] for c in contacts] == ["responsible", "relayed"]


# --- changing one's own basis (FR-K2, BR-10) --------------------------------------------------------------


def test_change_own_basis_is_logged_without_a_new_version(client, db_session):
    h = login(client, A)
    before = len(client.get(f"/entries/{PID}/history", headers=h).json())
    r = client.put(f"/entries/{PID}/my-basis", headers=h, json={"basis": "relayed", "source": "Team handbook"})
    assert r.status_code == 200 and r.json()["basis"] == "relayed"
    assert len(client.get(f"/entries/{PID}/history", headers=h).json()) == before  # no new version
    d = _detail(client, B, PID)
    assert d["current_version"]["version_number"] == 1 and d["current_version"]["status"] == "Unverified"

    log = client.get(f"/entries/{PID}/basis-log", headers=login(client, B)).json()
    assert len(log) == 1
    assert log[0]["user"]["display_name"] == "Employee A"
    assert (log[0]["old_basis"], log[0]["new_basis"], log[0]["new_source"]) == ("responsible", "relayed", "Team handbook")

    # Same value again changes nothing and logs nothing
    client.put(f"/entries/{PID}/my-basis", headers=h, json={"basis": "relayed", "source": "Team handbook"})
    assert len(client.get(f"/entries/{PID}/basis-log", headers=h).json()) == 1


def test_basis_change_keeps_verification(client):
    pid = _create(client, A).json()["public_id"]
    vid = _detail(client, A, pid)["current_version"]["id"]
    assert client.post(f"/approvals/{vid}/verify", headers=login(client, SENIOR)).status_code == 200
    client.put(f"/entries/{pid}/my-basis", headers=login(client, A), json={"basis": "relayed", "source": "Law"})
    assert _detail(client, A, pid)["current_version"]["status"] == "Verified"


def test_only_a_contact_can_change_their_own_basis(client):
    r = client.put(f"/entries/{PID}/my-basis", headers=login(client, B), json={"basis": "responsible"})
    assert r.status_code == 403
    r = client.put(f"/entries/{PID}/my-basis", headers=login(client, A), json={"basis": "relayed"})
    assert r.status_code == 422  # relayed needs a source
    assert client.put("/entries/NOPE/my-basis", headers=login(client, A), json={"basis": "responsible"}).status_code == 404


def test_basis_log_is_append_only(client, db_session):
    client.put(f"/entries/{PID}/my-basis", headers=login(client, A), json={"basis": "relayed", "source": "Law"})
    row = db_session.scalars(select(EntryContactChange)).first()
    row.new_source = "tampered"
    try:
        db_session.commit()
        raise AssertionError("update should be refused")
    except RuntimeError:
        db_session.rollback()


# --- pull requests (FR-K11) ---------------------------------------------------------------------------------


def test_pr_needs_a_basis(client):
    body = {"proposed_body": "Another sentence.", "change_note": "x"}
    assert client.post(f"/entries/{PID}/pull-requests", headers=login(client, B), json=body).status_code == 422
    body["basis"] = "relayed"
    assert client.post(f"/entries/{PID}/pull-requests", headers=login(client, B), json=body).status_code == 422
    body["basis_source"] = "Payroll newsletter"
    r = client.post(f"/entries/{PID}/pull-requests", headers=login(client, B), json=body)
    assert r.status_code == 201 and r.json()["basis"] == "relayed"


def test_pr_author_becomes_contact_only_once_merged(client):
    body = {"proposed_body": "Another sentence.", "change_note": "x", "basis": "relayed", "basis_source": "Newsletter"}
    pr = client.post(f"/entries/{PID}/pull-requests", headers=login(client, B), json=body).json()
    assert [c["user"]["id"] for c in _detail(client, C, PID)["contacts"]] == [A]
    assert client.post(f"/pull-requests/{pr['id']}/approve", headers=login(client, A)).status_code == 200
    contacts = _detail(client, C, PID)["contacts"]
    assert [(c["user"]["id"], c["role"], c["basis"], c["source"]) for c in contacts] == [
        (A, "author", "responsible", None), (B, "contributor", "relayed", "Newsletter")]


def test_verifier_sees_basis_in_the_approval_tab(client):
    pid = _create(client, A, basis="relayed", basis_source="Handbook").json()["public_id"]
    items = client.get("/approvals/pending", headers=login(client, SENIOR)).json()
    entry = next(i["entry"] for i in items if i["entry"]["public_id"] == pid)
    assert entry["contacts"][0]["basis"] == "relayed" and entry["contacts"][0]["source"] == "Handbook"


# --- search marker (FR-K12) -----------------------------------------------------------------------------------


def test_search_marks_entries_with_a_responsible_contact(client):
    resp = _create(client, A, title="Zebra responsible rule").json()["public_id"]
    rel = _create(client, A, title="Zebra relayed rule", basis="relayed", basis_source="Law").json()["public_id"]
    rows = client.get("/search", params={"q": "zebra"}, headers=login(client, B)).json()
    marks = {r["public_id"]: r["has_responsible_contact"] for r in rows}
    assert marks == {resp: True, rel: False}


# --- Responsibilities tab (FR-K8, FR-K9, FR-K10) ----------------------------------------------------------------


def test_responsibilities_tab_groups_entries_and_areas(client):
    _create(client, A, title="Rule one", keywords=["cut-off"])
    _create(client, A, title="Rule two", basis="relayed", basis_source="Newsletter")
    r = client.get(f"/people/{A}/responsibilities", headers=login(client, B))
    assert r.status_code == 200
    data = r.json()
    assert {i["title"] for i in data["responsible"]} == {"Belgian freelancer DMFA filing deadline", "Rule one"}
    assert [(i["title"], i["source"], i["role"]) for i in data["relayed"]] == [("Rule two", "Newsletter", "author")]
    assert data["areas"]["categories"] == ["Freelance / contractor payroll"]
    assert data["areas"]["countries"] == ["BE"]
    assert {t["name"] for t in data["areas"]["tags"]} >= {"cut-off", "dmfa"}
    assert client.get("/people/999/responsibilities", headers=login(client, B)).status_code == 404


def test_responsibilities_include_company_scopes(client):
    company = next(c for c in client.get("/companies", headers=login(client, A)).json() if c["name"] == "Northwind Logistics")
    _create(client, A, title="Client rule", scope="company", company_id=company["id"])
    areas = client.get(f"/people/{A}/responsibilities", headers=login(client, B)).json()["areas"]
    assert areas["companies"] == ["Northwind Logistics"]


def test_change_basis_for_several_entries_at_once(client):
    h = login(client, A)
    e2 = _create(client, A, title="Rule two").json()["public_id"]
    r = client.patch("/me/responsibilities", headers=h, json={
        "public_ids": [PID, e2], "basis": "relayed", "source": "Team handbook of my new team"})
    assert r.status_code == 200 and r.json()["changed"] == 2
    data = client.get(f"/people/{A}/responsibilities", headers=h).json()
    assert data["responsible"] == [] and len(data["relayed"]) == 2
    assert all(i["source"] == "Team handbook of my new team" for i in data["relayed"])
    assert len(client.get(f"/entries/{PID}/basis-log", headers=h).json()) == 1


def test_bulk_change_is_all_or_nothing_and_own_only(client):
    h = login(client, A)
    other = _create(client, B, title="B's rule").json()["public_id"]
    r = client.patch("/me/responsibilities", headers=h, json={
        "public_ids": [PID, other], "basis": "relayed", "source": "Law"})
    assert r.status_code == 403
    assert _detail(client, A, PID)["my_contact"]["basis"] == "responsible"  # rolled back
    assert client.patch("/me/responsibilities", headers=h, json={
        "public_ids": [PID], "basis": "relayed"}).status_code == 422
    assert client.patch("/me/responsibilities", headers=h, json={
        "public_ids": ["NOPE"], "basis": "responsible"}).status_code == 404


# --- contributors who are not verifiers ---------------------------------------------------------------------------


def test_contacts_cannot_verify_the_entry(client, db_session):
    from app.models import EntryContact, Entry

    pid = _create(client, A).json()["public_id"]
    entry = db_session.query(Entry).filter_by(public_id=pid).one()
    db_session.add(EntryContact(entry_id=entry.id, user_id=SENIOR, role="co_author", basis="relayed", source="Meeting"))
    db_session.commit()
    vid = _detail(client, A, pid)["current_version"]["id"]
    assert client.post(f"/approvals/{vid}/verify", headers=login(client, SENIOR)).status_code == 403
    assert client.post(f"/approvals/{vid}/verify", headers=login(client, TEAM_LEAD)).status_code == 200
