from sqlalchemy import select

from app.models import Entry, Tag, entry_tags
from app.services import tags as tag_service
from tests.conftest import login

A, B, C, SENIOR, TEAM_LEAD, MANAGER, ADMIN = 1, 2, 3, 4, 5, 6, 7


def _create(client, uid, title="Cut-off rule", keywords=None, country="BE", **extra):
    body = {
        "title": title,
        "body": "A rule about cut-off dates.",
        "category_id": 1,
        "country": country,
        "scope": "country",
        "basis": "responsible",
        "keywords": keywords or [],
    }
    body.update(extra)
    return client.post("/entries", headers=login(client, uid), json=body)


def _tags(entry_json):
    return {t["name"]: t["tag_type"] for t in entry_json["tags"]}


# --- normalization (FR-T1) -------------------------------------------------------------------


def test_normalize_tag():
    assert tag_service.normalize_tag("  Cut-Off   Date ") == "cut-off date"
    assert tag_service.normalize_tag(None) == "" and tag_service.normalize_tag("   ") == ""


def test_keywords_are_normalized_and_shared(client, db_session):
    first = _create(client, A, keywords=["  Cut-Off ", "INVOICE", "invoice"]).json()
    second = _create(client, B, title="Other", keywords=["cut-off"]).json()
    keywords = {n for n, t in _tags(first).items() if t == "keyword"}
    assert keywords == {"cut-off", "invoice"}  # duplicates collapse
    assert _tags(second)["cut-off"] == "keyword"

    tags = db_session.query(Tag).filter_by(name="cut-off").all()
    assert len(tags) == 1  # one shared entity, linked to both entries
    linked = db_session.execute(select(entry_tags.c.entry_id).where(entry_tags.c.tag_id == tags[0].id)).all()
    assert len(linked) == 2


def test_automatic_tags_have_their_own_type(client):
    entry = _create(client, A).json()
    tags = _tags(entry)
    auto = {n for n, t in tags.items() if t == "automatic"}
    kinds = {n.split(":")[0] for n in auto}
    assert kinds == {"country", "date", "author", "department", "role"}  # FR-E2
    assert "country:be" in auto and "author:employee a" in auto and "department:payroll" in auto


def test_keywords_cannot_use_system_prefixes_or_be_too_long(client):
    for bad in ("author:me", "Country:BE", "x" * 65):
        r = _create(client, A, keywords=[bad])
        assert r.status_code == 422, bad
    # nothing was half-created
    assert client.get("/search", headers=login(client, A)).json()[0]["public_id"] == "PP-BE-FRE-00001"
    assert len(client.get("/search", headers=login(client, A)).json()) == 1


def test_editing_a_draft_keeps_automatic_tags_and_replaces_keywords(client):
    entry = _create(client, A, keywords=["one", "two"]).json()
    r = client.patch(f"/entries/{entry['public_id']}", headers=login(client, A), json={"keywords": ["Three"]})
    assert r.status_code == 200, r.text
    tags = _tags(r.json())
    assert {n for n, t in tags.items() if t == "keyword"} == {"three"}
    assert {n.split(":")[0] for n, t in tags.items() if t == "automatic"} == {"country", "date", "author", "department", "role"}


# --- suggestions (FR-T2) ---------------------------------------------------------------------


def test_tag_suggestions(client):
    _create(client, A, keywords=["cut-off", "cutover"])
    _create(client, B, title="Second", keywords=["cut-off"])
    h = login(client, C)

    r = client.get("/tags", params={"q": "CUT"}, headers=h)
    assert r.status_code == 200
    assert [t["name"] for t in r.json()] == ["cut-off", "cutover"]  # most used first
    assert r.json()[0]["entry_count"] == 2 and r.json()[0]["tag_type"] == "keyword"

    assert [t["name"] for t in client.get("/tags", params={"q": "over"}, headers=h).json()] == ["cutover"]
    assert client.get("/tags", params={"q": "nothing-like-this"}, headers=h).json() == []
    kw_only = client.get("/tags", params={"type": "keyword", "limit": 50}, headers=h).json()
    assert kw_only and all(t["tag_type"] == "keyword" for t in kw_only)
    autos = client.get("/tags", params={"type": "automatic", "q": "author:"}, headers=h).json()
    assert autos and all(t["name"].startswith("author:") for t in autos)
    assert client.get("/tags", params={"type": "bogus"}, headers=h).status_code == 422
    assert client.get("/tags").status_code == 401


# --- search by tag (FR-T3/T4, FR-S5/S6) -------------------------------------------------------


def _search(client, params, uid=A):
    r = client.get("/search", params=params, headers=login(client, uid))
    assert r.status_code == 200, r.text
    return [e["public_id"] for e in r.json()]


def test_search_filters_by_tag(client):
    e2 = _create(client, B, title="Cut-off rule", keywords=["cut-off"]).json()["public_id"]
    e3 = _create(client, C, title="Invoices", keywords=["invoice"], country="NL").json()["public_id"]
    assert _search(client, {"tag": "cut-off"}) == [e2]
    assert _search(client, {"tag": "  Cut-Off "}) == [e2]  # normalized like the tag itself
    assert set(_search(client, {"tag": ["cut-off", "invoice"]})) == {e2, e3}  # one filter: OR
    assert _search(client, {"tag": "nope"}) == []
    # combined with the text query and other filters
    assert _search(client, {"tag": ["cut-off", "invoice"], "q": "invoices"}) == [e3]
    assert _search(client, {"tag": ["cut-off", "invoice"], "country": "NL"}) == [e3]
    assert _search(client, {"tag": "cut-off", "country": "NL"}) == []
    # automatic tags work as filters too
    assert _search(client, {"tag": "country:nl"}) == [e3]
    assert set(_search(client, {"tag": "author:employee b"})) == {e2}


def test_approvals_and_profiles_carry_tags(client):
    pid = _create(client, B, keywords=["cut-off"]).json()["public_id"]
    pending = client.get("/approvals/pending", headers=login(client, SENIOR)).json()
    item = next(p for p in pending if p["entry"]["public_id"] == pid)
    assert "cut-off" in {t["name"] for t in item["entry"]["tags"]}

    profile = client.get(f"/people/{B}", headers=login(client, A)).json()
    entry = next(e for e in profile["entries"] if e["public_id"] == pid)
    assert "cut-off" in {t["name"] for t in entry["tags"]}


# --- admin rename and merge (FR-T5) -----------------------------------------------------------


def _tag_id(client, name):
    return next(t["id"] for t in client.get("/tags", params={"q": name, "limit": 50}, headers=login(client, ADMIN)).json()
                if t["name"] == name)


def test_admin_renames_a_tag_and_keeps_its_links(client):
    pid = _create(client, A, keywords=["cutoff"]).json()["public_id"]
    tid = _tag_id(client, "cutoff")
    admin = login(client, ADMIN)

    assert client.patch(f"/admin/tags/{tid}", json={"name": "cut-off"}, headers=login(client, A)).status_code == 403
    r = client.patch(f"/admin/tags/{tid}", json={"name": "  Cut-Off Date "}, headers=admin)
    assert r.status_code == 200 and r.json()["name"] == "cut-off date" and r.json()["entry_count"] == 1
    assert "cut-off date" in _tags(client.get(f"/entries/{pid}", headers=admin).json())
    assert _search(client, {"tag": "cut-off date"}) == [pid]
    assert _search(client, {"tag": "cutoff"}) == []

    # clashes, system prefixes and automatic tags
    other = _create(client, B, title="Other", keywords=["invoice"]).json()
    inv = _tag_id(client, "invoice")
    assert client.patch(f"/admin/tags/{inv}", json={"name": "cut-off date"}, headers=admin).status_code == 409
    assert client.patch(f"/admin/tags/{inv}", json={"name": "author:x"}, headers=admin).status_code == 422
    auto = next(t["id"] for t in other["tags"] if t["tag_type"] == "automatic")
    assert client.patch(f"/admin/tags/{auto}", json={"name": "whatever"}, headers=admin).status_code == 422
    assert client.patch("/admin/tags/9999", json={"name": "x"}, headers=admin).status_code == 404


def test_admin_merges_tags(client):
    both = _create(client, A, title="Both", keywords=["cutoff", "cut-off"]).json()["public_id"]
    only_old = _create(client, B, title="Old", keywords=["cutoff"]).json()["public_id"]
    admin = login(client, ADMIN)
    old, new = _tag_id(client, "cutoff"), _tag_id(client, "cut-off")

    assert client.post(f"/admin/tags/{old}/merge", json={"into_id": new}, headers=login(client, A)).status_code == 403
    assert client.post(f"/admin/tags/{old}/merge", json={"into_id": old}, headers=admin).status_code == 422
    r = client.post(f"/admin/tags/{old}/merge", json={"into_id": new}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "cut-off" and r.json()["entry_count"] == 2  # no duplicate link for "Both"

    assert set(_search(client, {"tag": "cut-off"})) == {both, only_old}
    assert _search(client, {"tag": "cutoff"}) == []
    assert {t["name"] for t in client.get("/tags", params={"q": "cutoff"}, headers=admin).json()} == set()
    assert client.post(f"/admin/tags/{old}/merge", json={"into_id": new}, headers=admin).status_code == 404

    auto = next(t["id"] for t in client.get(f"/entries/{both}", headers=admin).json()["tags"] if t["tag_type"] == "automatic")
    assert client.post(f"/admin/tags/{new}/merge", json={"into_id": auto}, headers=admin).status_code == 422


# --- cleanup of tags created before they were entities ---------------------------------------


def test_normalize_existing_tags(client, db_session):
    entry = db_session.query(Entry).filter_by(public_id="PP-BE-FRE-00001").one()
    legacy = [Tag(name="Dmfa-Legacy", tag_type="keyword"), Tag(name="Author:Employee A", tag_type="keyword")]
    dupe = Tag(name=" DMFA", tag_type="keyword")  # same tag as the seeded "dmfa", spelled differently
    db_session.add_all(legacy + [dupe])
    db_session.flush()
    entry.tags.extend(legacy + [dupe])
    db_session.commit()

    changed = tag_service.normalize_existing_tags(db_session)
    assert changed > 0
    names = {t.name: t.tag_type for t in db_session.query(Tag).all()}
    assert "Dmfa-Legacy" not in names and names["dmfa-legacy"] == "keyword"
    assert "Author:Employee A" not in names and names["author:employee a"] == "automatic"
    assert names["country:be"] == "automatic"  # missing country tag backfilled
    assert db_session.query(Tag).filter_by(name="dmfa").count() == 1

    assert tag_service.normalize_existing_tags(db_session) == 0  # idempotent
