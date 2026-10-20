import json
import subprocess
from datetime import date

import pytest

from app import config
from app.ai_parser import cursor_cli, pipeline
from app.ai_parser.cursor_cli import AgentReply, CursorCliError
from app.ai_parser.schema import AgentMeme
from app.ai_parser.sources import load_chat, meme_day, parse_vtt
from app.ai_parser.validate import check_meme, validate_reply
from tests.conftest import login

SOURCES = config.MOCK_DATA_DIR / "sources"
INDEX = {row["id"]: row for row in json.loads((SOURCES / "index.json").read_text(encoding="utf-8"))}


def expected(sid: str) -> dict:
    return json.loads((SOURCES / INDEX[sid]["expected"]).read_text(encoding="utf-8"))


def agent_memes(sid: str) -> list[dict]:
    """The expected memes as the agent answers them, without the fields the backend adds."""
    return [{k: v for k, v in m.items() if k not in ("source", "similar_entries")} for m in expected(sid)["memes"]]


def fake_runner(*answers):
    """Stands in for the Cursor CLI: returns the given answers in order and records each call."""
    calls = []

    def runner(workspace, prompt, resume):
        calls.append({"prompt": prompt, "resume": resume, "files": sorted(p.name for p in workspace.iterdir())})
        return AgentReply(data=answers[len(calls) - 1], session_id="sess-1")

    runner.calls = calls
    return runner


def test_parse_vtt():
    cues = parse_vtt(SOURCES / "meetings/m1-payroll-be-weekly.vtt")
    assert len(cues) == 58
    assert cues[0] == ("00:00:03", "Team Lead", "Morning everyone. Can you all hear me ok?")
    assert ("00:12:40", "Employee C", "Yes, that's right, it was in the payroll newsletter in September.") in cues


def test_load_chat_uses_final_text_and_hides_deleted_messages():
    c2 = load_chat(SOURCES / "chats/c2-contractor-announcements.json")
    update = c2.units_at("c2-007")[0]
    assert update.day == date(2026, 9, 29)
    assert "November run" in update.text
    assert "the 25th applies from the December run" not in c2.render()  # the text before the edit

    c3 = load_chat(SOURCES / "chats/c3-freelance-onboarding.json")
    assert c3.units_at("c3-011")[0].deleted
    assert "85.07.30" not in c3.render()


@pytest.mark.parametrize("sid", sorted(INDEX))
def test_expected_memes_pass_validation(db_session, sid):
    source = pipeline.source_from_index(db_session, INDEX[sid])
    memes, problems = validate_reply({"memes": expected(sid)["memes"]}, source)
    assert problems == []
    assert len(memes) == len(expected(sid)["memes"])


def test_meeting_guests_are_detected(db_session):
    source = pipeline.source_from_index(db_session, INDEX["m2"])
    assert source.guests == ["Lotte (Guest)"]


def test_chat_meme_goes_to_the_day_of_its_latest_quote():
    c2 = load_chat(SOURCES / "chats/c2-contractor-announcements.json")
    days = [meme_day(m, c2) for m in expected("c2")["memes"]]
    assert days == [date(2026, 9, 29), date(2026, 9, 22), date(2026, 10, 15)]


def test_validator_rejects_broken_memes(db_session):
    m1 = pipeline.source_from_index(db_session, INDEX["m1"])
    base = agent_memes("m1")[0]

    def errors(source, **changes):
        meme = json.loads(json.dumps(base))
        for path, value in changes.items():
            target = meme
            *keys, last = path.split("__")
            for key in keys:
                target = target[int(key)] if key.isdigit() else target[key]
            target[int(last) if last.isdigit() else last] = value
        return check_meme(AgentMeme.model_validate(meme), source)

    assert any("exact fragment" in e for e in errors(m1, quotes__0__text="goes into the next run."))
    assert any("not by" in e for e in errors(m1, quotes__0__at="00:12:40"))
    assert any("not a participant" in e for e in errors(m1, confirmed_by__0__user="lotte@client.example"))
    assert any("own meme" in e for e in errors(m1, confirmed_by__0__user="employee.a@sdworx.example"))
    # C's line at 00:08:40 comes before the statement at 00:12:31
    assert any("after the statement" in e for e in errors(
        m1, confirmed_by__0__quote={"text": "One of mine is waiting", "at": "00:08:40"}))
    assert any("needs a source" in e for e in errors(m1, confirmed_by__0__basis_hint={"basis": "relayed", "source": None}))

    c3 = load_chat(SOURCES / "chats/c3-freelance-onboarding.json")
    deleted = {
        **agent_memes("c3")[1],
        "speaker": "employee.b@sdworx.example",
        "quotes": [{"speaker": "employee.b@sdworx.example", "text": "is this ok to share", "at": "c3-011"}],
        "confirmed_by": [],
    }
    assert any("deleted" in e for e in check_meme(AgentMeme.model_validate(deleted), c3))


def test_pipeline_writes_one_file_per_meeting(db_session, tmp_path):
    source = pipeline.source_from_index(db_session, INDEX["m1"])
    runner = fake_runner({"memes": agent_memes("m1")})
    paths = pipeline.run_source(db_session, source, out_dir=tmp_path, runner=runner)

    assert paths == [tmp_path / "meetings" / "m1-payroll-be-weekly.json"]
    out = json.loads(paths[0].read_text(encoding="utf-8"))
    assert [m["id"] for m in out["memes"]] == [f"m1-payroll-be-weekly#{n}" for n in (1, 2, 3)]
    assert out["memes"][0]["source"] == {"type": "meeting", "title": "Payroll BE weekly", "date": "2026-10-14"}
    assert all(isinstance(m["similar_entries"], list) for m in out["memes"])
    assert out["rejected"] == [] and out["generator"]["tool"] == "cursor-agent"
    # The agent only ever sees these three files, never the repository
    assert runner.calls == [{"prompt": pipeline.PROMPT, "resume": None, "files": ["context.json", "instructions.md", "source.md"]}]


def test_pipeline_writes_one_file_per_chat_day(db_session, tmp_path):
    stale = tmp_path / "chats" / "c2-contractor-announcements" / "2026-01-01.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")

    source = pipeline.source_from_index(db_session, INDEX["c2"])
    paths = pipeline.run_source(db_session, source, out_dir=tmp_path, runner=fake_runner({"memes": agent_memes("c2")}))

    assert [p.name for p in paths] == ["2026-09-22.json", "2026-09-29.json", "2026-10-15.json"]
    assert not stale.exists()
    day = json.loads(paths[1].read_text(encoding="utf-8"))
    assert day["source"]["day"] == "2026-09-29"
    assert [m["id"] for m in day["memes"]] == ["c2-contractor-announcements@2026-09-29#1"]
    assert "November" in day["memes"][0]["statement"]


def test_pipeline_repairs_an_invalid_answer(db_session, tmp_path):
    source = pipeline.source_from_index(db_session, INDEX["m1"])
    broken = agent_memes("m1")
    broken[0]["quotes"][0]["text"] = "an invented quote"

    runner = fake_runner({"memes": broken}, {"memes": agent_memes("m1")})
    out = json.loads(pipeline.run_source(db_session, source, out_dir=tmp_path, runner=runner)[0].read_text())
    assert runner.calls[1]["resume"] == "sess-1"
    assert "meme 1: quote 1: text is not an exact fragment" in runner.calls[1]["prompt"]
    assert len(out["memes"]) == 3 and out["rejected"] == []

    runner = fake_runner({"memes": broken}, {"memes": broken})
    out = json.loads(pipeline.run_source(db_session, source, out_dir=tmp_path, runner=runner)[0].read_text())
    assert len(out["memes"]) == 2
    assert len(out["rejected"]) == 1 and "exact fragment" in out["rejected"][0]["errors"][0]


def test_pipeline_drops_low_confidence_memes(db_session, tmp_path):
    source = pipeline.source_from_index(db_session, INDEX["m1"])
    memes = agent_memes("m1")
    memes[2]["confidence"] = 0.3
    out = json.loads(pipeline.run_source(db_session, source, out_dir=tmp_path, runner=fake_runner({"memes": memes}))[0].read_text())
    assert len(out["memes"]) == 2
    assert "below 0.6" in out["rejected"][0]["errors"][0]


def test_cursor_cli_command_and_answer(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(cmd=cmd, cwd=kwargs["cwd"])
        envelope = {"type": "result", "subtype": "success", "is_error": False,
                    "result": '```json\n{"memes": []}\n```', "session_id": "abc"}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(envelope), stderr="")

    monkeypatch.setattr(cursor_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(config.settings, "cursor_model", "some-model")
    reply = cursor_cli.run_agent(tmp_path, "hello", resume="abc")

    assert reply.data == {"memes": []} and reply.session_id == "abc"
    cmd = seen["cmd"]
    assert cmd[:4] == ["agent", "-p", "--output-format", "json"]
    assert cmd[cmd.index("--mode") + 1] == "ask" and "--force" not in cmd
    assert cmd[cmd.index("--workspace") + 1] == str(tmp_path) and seen["cwd"] == tmp_path
    assert cmd[cmd.index("--model") + 1] == "some-model"
    assert cmd[cmd.index("--resume") + 1] == "abc" and cmd[-1] == "hello"


def test_cursor_cli_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(cursor_cli.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Not logged in"))
    with pytest.raises(CursorCliError, match="Not logged in"):
        cursor_cli.run_agent(tmp_path, "hello")

    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(cursor_cli.subprocess, "run", missing)
    with pytest.raises(CursorCliError, match="not found"):
        cursor_cli.run_agent(tmp_path, "hello")

    with pytest.raises(CursorCliError, match="no JSON object"):
        cursor_cli.parse_answer("I could not find any memes.")


def test_upload_meeting_stores_memes_in_the_database(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMES_DIR", tmp_path)
    monkeypatch.setattr(cursor_cli, "run_agent", fake_runner({"memes": agent_memes("m1")}))
    team_lead = login(client, 5)
    vtt = (SOURCES / "meetings/m1-payroll-be-weekly.vtt").read_bytes()
    form = {"type": "meeting", "title": "Payroll BE weekly", "date": "2026-10-14", "participant_ids": ["1", "2", "3", "6"]}

    r = client.post("/parser/sources", headers=team_lead, files={"file": ("transcript.vtt", vtt, "text/vtt")}, data=form)
    assert r.status_code == 202, r.text
    run_id = r.json()["id"]

    run = client.get(f"/parser/runs/{run_id}", headers=team_lead).json()
    assert run["status"] == "done", run
    assert run["memes"] == 3 and run["source_id"] == "2026-10-14-payroll-be-weekly"
    assert not (tmp_path / "meetings").exists()  # real uploads go to the database, not to the demo files
    assert not (tmp_path / "_uploads" / run_id).exists()  # the raw transcript is not kept
    assert client.get(f"/parser/runs/{run_id}", headers=login(client, 2)).status_code == 404

    mine = client.get("/memes", headers=team_lead).json()
    assert [m["my_request"]["status"] for m in mine] == ["pending"]

    again = client.post("/parser/sources", headers=team_lead, files={"file": ("transcript.vtt", vtt, "text/vtt")}, data=form)
    assert again.status_code == 409


def test_upload_chat_requires_membership(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMES_DIR", tmp_path)
    chat = (SOURCES / "chats/c1-payroll-be-questions.json").read_bytes()
    r = client.post(
        "/parser/sources", headers=login(client, 7),  # Admin is not in this chat
        files={"file": ("chat.json", chat, "application/json")}, data={"type": "chat"},
    )
    assert r.status_code == 403
    assert list((tmp_path / "_uploads").iterdir()) == []
