import json
from datetime import date

from app import config
from app.ai_parser import pipeline
from app.ai_parser.cursor_cli import AgentReply
from app.ai_parser.store import save_memes
from app.models import AuthorshipRequest, Meme, MemeSource, Notification
from tests.conftest import login

SOURCES = config.MOCK_DATA_DIR / "sources"
INDEX = {row["id"]: row for row in json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))}
A, B, C, EXPERT, TEAM_LEAD, MANAGER, ADMIN = range(1, 8)


def expected(sid: str) -> list[dict]:
    return json.loads((SOURCES / INDEX[sid]["expected"]).read_text(encoding="utf-8"))["memes"]


def store(db, sid: str) -> MemeSource:
    """Stores the expected memes of a mock source as if the agent had produced them."""
    row = INDEX[sid]
    if row["type"] == "meeting":
        participants, dates = row["participants"], {"meeting_date": date.fromisoformat(row["date"])}
    else:
        chat = json.loads((SOURCES / row["file"]).read_text(encoding="utf-8"))
        participants = [m["email"] for m in chat["members"]]
        dates = {"date_from": date.fromisoformat(row["date_from"]), "date_to": date.fromisoformat(row["date_to"])}
    memes = [{**m, "id": f"{sid}#{n}"} for n, m in enumerate(expected(sid), 1)]
    source = save_memes(db, key=sid, type=row["type"], title=row["title"], participants=participants, memes=memes, **dates)
    db.close()  # no open read transaction while the API is called (StaticPool)
    return source


def ids(memes: list[dict]) -> list[str]:
    return [m["key"] for m in memes]


def test_store_asks_speakers_and_confirmers(client, db_session):
    store(db_session, "c1")
    requests = db_session.query(AuthorshipRequest).all()
    # c1: #1 Senior Expert + C, #2 A, #3 Team Lead + A
    assert sorted((r.meme.key, r.user_id, r.role) for r in requests) == [
        ("c1#1", C, "confirmer"), ("c1#1", EXPERT, "speaker"),
        ("c1#2", A, "speaker"),
        ("c1#3", A, "confirmer"), ("c1#3", TEAM_LEAD, "speaker"),
    ]
    assert all(r.status == "pending" for r in requests)
    notes = {n.user_id: n for n in db_session.query(Notification).filter(Notification.event_type.in_(["authorship_request", "memes_ready"]))}
    assert notes[A].event_type == "authorship_request" and notes[A].title.startswith("2 memes")
    assert notes[B].event_type == "memes_ready"  # B is in the chat but has no request
    assert set(notes) == {A, B, C, EXPERT, TEAM_LEAD}


def test_only_participants_see_memes(client, db_session):
    store(db_session, "m1")
    meme_id = db_session.query(Meme).filter(Meme.key == "m1#1").one().id
    for outsider in (EXPERT, ADMIN):
        h = login(client, outsider)
        assert client.get("/memes", headers=h).json() == []
        assert client.get("/memes?tab=colleagues", headers=h).json() == []
        assert client.get(f"/memes/{meme_id}", headers=h).status_code == 404


def test_my_memes_and_colleagues_memes(client, db_session):
    store(db_session, "m1")  # #1 A + C, #2 Team Lead + Manager, #3 B
    store(db_session, "c1")
    a = login(client, A)
    assert ids(client.get("/memes?type=meeting", headers=a).json()) == ["m1#1"]
    assert ids(client.get("/memes?tab=colleagues&type=meeting", headers=a).json()) == ["m1#3", "m1#2"]
    assert ids(client.get("/memes?tab=colleagues&type=chat", headers=a).json()) == ["c1#1"]
    assert len(client.get("/memes?tab=colleagues&type=meeting&type=chat", headers=a).json()) == 3

    c = client.get("/memes?type=meeting", headers=login(client, C)).json()[0]
    assert c["my_request"] == {"role": "confirmer", "status": "pending",
                               "basis_hint": {"basis": "relayed", "source": "Payroll newsletter, September 2026"}}
    assert c["speaker"]["display_name"] == "Employee A" and c["statement"].startswith("Contractor invoices")


def test_accept_prepares_the_meme_and_tells_the_others(client, db_session):
    store(db_session, "m1")
    meme_id = db_session.query(Meme).filter(Meme.key == "m1#1").one().id
    c = login(client, C)
    assert [m["key"] for m in client.get("/memes/requests/pending", headers=c).json()] == ["m1#1"]

    assert client.post(f"/memes/{meme_id}/accept", headers=c, json={"basis": "relayed"}).status_code == 422
    r = client.post(f"/memes/{meme_id}/accept", headers=c, json={"basis": "relayed", "source": "Payroll newsletter"})
    assert r.status_code == 200, r.text
    meme = r.json()
    assert meme["status"] == "preparing"
    assert [(x["user"]["id"], x["status"], x["basis"]) for x in meme["candidates"]] == [(A, "pending", None), (C, "accepted", "relayed")]
    assert client.get("/memes/requests/pending", headers=c).json() == []
    assert client.post(f"/memes/{meme_id}/accept", headers=c, json={"basis": "responsible"}).status_code == 409

    note = db_session.query(Notification).filter(Notification.user_id == A, Notification.event_type == "authorship_accepted").one()
    assert note.title.startswith("Employee C accepted")
    assert client.post(f"/memes/{meme_id}/accept", headers=login(client, B), json={"basis": "responsible"}).status_code == 403
    assert client.post(f"/memes/{meme_id}/accept", headers=login(client, EXPERT), json={"basis": "responsible"}).status_code == 404


def test_meme_is_declined_when_every_candidate_declines(client, db_session):
    store(db_session, "m1")
    meme_id = db_session.query(Meme).filter(Meme.key == "m1#2").one().id
    r = client.post(f"/memes/{meme_id}/decline", headers=login(client, TEAM_LEAD), json={"reason": "not_relevant"})
    assert r.json()["status"] == "new"
    r = client.post(f"/memes/{meme_id}/decline", headers=login(client, MANAGER), json={})
    assert r.json()["status"] == "declined"
    assert [x["decline_reason"] for x in r.json()["candidates"]] == ["not_relevant", None]
    assert client.post(f"/memes/{meme_id}/decline", headers=login(client, MANAGER), json={}).status_code == 409


def test_demo_memes_are_seeded_from_the_files_once(client, db_session, monkeypatch, tmp_path):
    from app import seeds as seeds_mod

    monkeypatch.setattr(config, "MEMES_DIR", tmp_path)
    for sid in ("m1", "c2"):
        answer = [{k: v for k, v in m.items() if k not in ("source", "similar_entries")} for m in expected(sid)]
        source = pipeline.source_from_index(db_session, INDEX[sid])
        pipeline.run_source(db_session, source, runner=lambda ws, prompt, resume, a=answer: AgentReply({"memes": a}, None))
    db_session.close()

    seeds_mod.seed_demo_memes()
    seeds_mod.seed_demo_memes()
    keys = {s.key: s for s in db_session.query(MemeSource)}
    assert set(keys) == {"m1-payroll-be-weekly", "c2-contractor-announcements"}
    chat_memes = db_session.query(Meme).filter(Meme.source_id == keys["c2-contractor-announcements"].id).order_by(Meme.day).all()
    assert [m.day for m in chat_memes] == [date(2026, 9, 22), date(2026, 9, 29), date(2026, 10, 15)]
    assert db_session.query(Meme).count() == 6
