import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
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
    monkeypatch.setattr(settings, "seed_history_demo", False)

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


@pytest.fixture()
def db_session(client):
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def history_entry(client, db_session) -> str:
    """A 3-version entry (same shape as the startup demo seed); returns its public id."""
    from app.seeds import _insert_demo_entry

    public_id = _insert_demo_entry(db_session)
    db_session.commit()
    db_session.close()  # no open read transaction while the API is called (StaticPool)
    return public_id


def login(client: TestClient, user_id: int) -> dict:
    r = client.post("/auth/dev-login", json={"user_id": user_id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token"]
    return {"Authorization": f"Bearer {data['token']}"}
