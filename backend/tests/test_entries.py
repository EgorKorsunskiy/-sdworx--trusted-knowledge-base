import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.seeds import seed_all


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Point seed engine to in-memory by seeding directly
    from app import seeds as seeds_mod
    from app import database as db_mod

    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(seeds_mod, "engine", engine)

    with TestingSession() as db:
        # inline seed using shared engine
        seed_all()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client: TestClient, user_id: int) -> dict:
    r = client.post("/auth/dev-login", json={"user_id": user_id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token"]
    return {"Authorization": f"Bearer {data['token']}"}


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
            "scope": "country-specific",
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
            "scope": "EU-wide",
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
