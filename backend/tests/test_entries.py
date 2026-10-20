from tests.conftest import login
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_entry_and_public_id(client):
    headers = login(client, 1)
    bad = client.post(
        "/entries",
        headers=headers,
        json={
            "title": "",
            "body": "x",
            "category_id": 1,
            "country": "BE",
            "scope": "country",
        },
    )
    assert bad.status_code == 422

    ok = client.post(
        "/entries",
        headers=headers,
        json={
            "title": "EU contractor travel rules",
            "body": "Travel day rates for contractors follow local labor guidance.",
            "justification": "HR handbook",
            "category_id": 1,
            "country": "BE",
            "scope": "eu",
            "basis": "responsible",
            "keywords": ["travel", "contractor"],
        },
    )
    assert ok.status_code == 201, ok.text
    data = ok.json()
    assert data["public_id"].startswith("PP-BE-FRE-")
    assert data["current_version"]["status"] == "Unverified"
    assert data["can_edit"] is True
    tag_names = [t["name"] for t in data["tags"]]
    assert any(t.startswith("author:") for t in tag_names)
    assert "travel" in tag_names


def test_author_edits_unverified_others_cannot(client):
    headers_a = login(client, 1)
    headers_b = login(client, 2)

    r = client.get("/entries/PP-BE-FRE-00001", headers=headers_a)
    assert r.status_code == 200
    assert r.json()["can_edit"] is True
    assert r.json()["current_version"]["status"] == "Unverified"
    assert len(r.json()["who_to_ask"]) >= 1

    patch = client.patch(
        "/entries/PP-BE-FRE-00001",
        headers=headers_a,
        json={"title": "Updated DMFA filing deadline"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["current_version"]["title"] == "Updated DMFA filing deadline"
    assert patch.json()["current_version"]["version_number"] == 1

    deny = client.patch(
        "/entries/PP-BE-FRE-00001",
        headers=headers_b,
        json={"title": "Hijack"},
    )
    assert deny.status_code == 403

    ver = client.get("/entries/PP-BE-FRE-00001/versions/1", headers=headers_a)
    assert ver.status_code == 200
    assert ver.json()["version_number"] == 1


def _payload(**extra):
    return {
        "title": "Contractor rules outside BE",
        "body": "Rules for contractors working outside Belgium.",
        "category_id": 1,
        "country": "BE",
        "scope": "country",
        "basis": "responsible",
        **extra,
    }


def test_create_entry_with_difference_note(client):
    headers = login(client, 1)
    r = client.post(
        "/entries",
        headers=headers,
        json=_payload(difference_note="  Covers contractors outside BE  "),
    )
    assert r.status_code == 201, r.text
    assert r.json()["difference_note"] == "Covers contractors outside BE"
    got = client.get(f"/entries/{r.json()['public_id']}", headers=headers)
    assert got.json()["difference_note"] == "Covers contractors outside BE"


def test_create_entry_without_note(client):
    headers = login(client, 1)
    r = client.post("/entries", headers=headers, json=_payload())
    assert r.status_code == 201, r.text
    assert r.json()["difference_note"] is None
    r = client.post("/entries", headers=headers, json=_payload(difference_note="   "))
    assert r.status_code == 201, r.text
    assert r.json()["difference_note"] is None


def test_note_in_pending_for_verifier(client):
    r = client.post(
        "/entries", headers=login(client, 1), json=_payload(difference_note="Different scope")
    )
    public_id = r.json()["public_id"]
    pending = client.get("/approvals/pending", headers=login(client, 4))
    assert pending.status_code == 200, pending.text
    notes = {i["entry"]["public_id"]: i["entry"]["difference_note"] for i in pending.json()}
    assert notes[public_id] == "Different scope"
    assert notes["PP-BE-FRE-00001"] is None


def test_note_hidden_from_non_verifier(client):
    r = client.post(
        "/entries", headers=login(client, 1), json=_payload(difference_note="Secret-ish note")
    )
    url = f"/entries/{r.json()['public_id']}"
    assert client.get(url, headers=login(client, 2)).json()["difference_note"] is None
    assert client.get(url).status_code == 401  # signing in is required to read entries
    assert client.get(url, headers=login(client, 4)).json()["difference_note"] == "Secret-ish note"


def test_note_too_long_rejected(client):
    headers = login(client, 1)
    r = client.post("/entries", headers=headers, json=_payload(difference_note="x" * 1001))
    assert r.status_code == 422
    r = client.post("/entries", headers=headers, json=_payload(difference_note="x" * 1000))
    assert r.status_code == 201, r.text


def test_ensure_columns_adds_missing_column():
    from sqlalchemy import inspect, text

    from app.database import _ensure_columns

    eng = create_engine("sqlite://", poolclass=StaticPool)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE entries (id INTEGER PRIMARY KEY)"))
    _ensure_columns(eng)
    assert "difference_note" in {c["name"] for c in inspect(eng).get_columns("entries")}
    _ensure_columns(eng)  # idempotent
    assert "difference_note" in {c["name"] for c in inspect(eng).get_columns("entries")}
