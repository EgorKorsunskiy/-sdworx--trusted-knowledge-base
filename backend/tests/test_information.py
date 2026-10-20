"""AI parser: Information overview (Yours / Others), decisions with history, visibility, co-authorship."""

import pytest

from tests.conftest import login

A, B, C, SENIOR, TEAM_LEAD, MANAGER, ADMIN = 1, 2, 3, 4, 5, 6, 7
CUTOFF = "Cut-off date for contractor invoices"  # m1 (meeting): speaker A, confirmer C; also c2 (chat): TL + C
VIES = "Check a new contractor's VAT number in VIES"  # m1: speaker B, no confirmers
SECTIONS = ("to_decide", "postponed", "decided", "coauthor")


@pytest.fixture()
def parser(client, db_session):
    """The six mock sources, imported by the stub agent."""
    from app.services.parser_agent import load_mock_sources

    assert load_mock_sources(db_session) == 6
    db_session.close()
    return client


def _get(client, uid, url, **kw):
    return client.get(url, headers=login(client, uid), **kw)


def _post(client, uid, url, json=None):
    return client.post(url, headers=login(client, uid), json=json)


def _items(client, uid, tab="yours", section="to_decide", **params):
    r = _get(client, uid, "/information", params={"tab": tab, "section": section, "page_size": 50, **params})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _titles(client, uid, tab="yours", section="to_decide", source="Payroll BE weekly"):
    """Titles of the memes of one source in a tab section (CUTOFF also exists in another source)."""
    return {
        i["meme"]["title"] for i in _items(client, uid, tab, section) if i["meme"]["source"]["title"] == source
    }


def _meme(client, uid, title, source=None, tab="yours"):
    """The meme item with this title as user uid sees it (searching every section of the tab)."""
    for section in SECTIONS if tab == "yours" else ("to_decide",):
        for it in _items(client, uid, tab, section):
            if it["meme"]["title"] == title and (source is None or it["meme"]["source"]["title"] == source):
                return it["meme"]
    raise AssertionError(f"{title!r} not found for user {uid} in {tab}")


def _mine(meme):
    return next(s for s in meme["suggestions"] if s["is_mine"])


def _approve(client, uid, sid, basis="responsible", source=None):
    return _post(client, uid, f"/information/suggestions/{sid}/approve", {"basis": basis, "source": source})


def _sug(client, uid, title, source=None):
    return _mine(_meme(client, uid, title, source))["id"]


# --- what the stub agent stores ---------------------------------------------------------------------------------


def test_agent_creates_one_suggestion_per_candidate(parser):
    meme = _meme(parser, A, CUTOFF, "Payroll BE weekly")
    assert meme["status"] == "new" and meme["speaker"]["display_name"] == "Employee A"
    assert [c["display_name"] for c in meme["confirmers"]] == ["Employee C"]
    owners = {s["owner"]["display_name"]: s["role"] for s in meme["suggestions"]}
    assert owners == {"Employee A": "speaker", "Employee C": "confirmer"}
    assert all(s["state"] == "pending" for s in meme["suggestions"])
    assert all(s["history"][0]["action"] == "created" for s in meme["suggestions"])
    assert meme["category"] == "Freelance / contractor payroll" and meme["scope"] == "country"
    assert {t["name"] for t in meme["tags"]} >= {"contractor", "invoice", "cut-off"}
    assert meme["source"]["kind"] == "meeting" and meme["quotes"]
    assert any(q["is_confirmation"] and q["user"]["display_name"] == "Employee C" for q in meme["quotes"])
    assert all(q["context"] for q in meme["quotes"])  # a few lines around each quote, cut at import


def test_low_confidence_and_unquoted_memes_are_dropped(client, db_session):
    from datetime import date

    from app.models import Meme
    from app.services.parser_agent import import_agent_output

    good = {"speaker": "employee.a@sdworx.example", "statement": "S", "confidence": 0.9,
            "quotes": [{"speaker": "employee.a@sdworx.example", "text": "x", "at": "00:00:01"}]}
    memes = [
        good,
        {**good, "confidence": 0.4},
        {**good, "quotes": []},
        {**good, "speaker": "nobody@sdworx.example"},
        {**good, "speaker": "admin@sdworx.example"},  # not a participant
    ]
    import_agent_output(db_session, kind="meeting", title="T", date_from=date(2026, 10, 1), date_to=None,
                        participant_emails=["employee.a@sdworx.example", "employee.b@sdworx.example"], memes=memes)
    db_session.commit()
    assert db_session.query(Meme).count() == 1


def test_confirmers_must_be_other_participants_with_a_quote(client, db_session):
    from datetime import date

    from app.models import Suggestion
    from app.services.parser_agent import import_agent_output

    q = {"speaker": "employee.a@sdworx.example", "text": "x", "at": "1"}
    meme = {"speaker": "employee.a@sdworx.example", "statement": "S", "confidence": 0.9, "quotes": [q],
            "confirmed_by": [
                {"user": "employee.a@sdworx.example", "quote": {"text": "me", "at": "2"}},  # the speaker
                {"user": "admin@sdworx.example", "quote": {"text": "hm", "at": "3"}},  # not a participant
                {"user": "employee.b@sdworx.example", "quote": {"text": "", "at": "4"}},  # no quote, no confirmer
                {"user": "employee.c@sdworx.example", "quote": {"text": "yes", "at": "5"}},
            ]}
    import_agent_output(db_session, kind="chat", title="T", date_from=date(2026, 10, 1), date_to=None,
                        participant_emails=["employee.a@sdworx.example", "employee.b@sdworx.example",
                                            "employee.c@sdworx.example"], memes=[meme])
    db_session.commit()
    assert sorted(s.user_id for s in db_session.query(Suggestion)) == [A, C]


def test_threshold_is_an_admin_setting(client, db_session):
    from app.models import SystemSetting
    from app.services.parser_agent import load_mock_sources
    from app.models import Meme

    row = db_session.query(SystemSetting).filter_by(key="parser_confidence_threshold").one()
    row.value = "0.87"
    db_session.commit()
    load_mock_sources(db_session)
    assert db_session.query(Meme).filter(Meme.confidence < 0.87).count() == 0


# --- visibility (FR-MS5, BR-M1) -------------------------------------------------------------------------------------


def test_only_participants_see_a_source(parser):
    meme = _meme(parser, A, CUTOFF, "Payroll BE weekly")
    for uid in (SENIOR, ADMIN):  # neither took part in that meeting
        assert _get(parser, uid, f"/information/memes/{meme['id']}").status_code == 404
        assert _get(parser, uid, f"/information/suggestions/{meme['suggestions'][0]['id']}").status_code == 404
        seen = {
            it["meme"]["source"]["title"]
            for tab in ("yours", "others") for sec in SECTIONS for it in _items(parser, uid, tab, sec)
        }
        assert "Payroll BE weekly" not in seen
    assert _get(parser, A, f"/information/memes/{meme['id']}").status_code == 200
    assert _get(parser, A, "/information/memes/99999").status_code == 404


def test_non_participants_cannot_decide_or_request(parser):
    meme = _meme(parser, A, CUTOFF, "Payroll BE weekly")
    sid = meme["suggestions"][0]["id"]
    assert _approve(parser, SENIOR, sid).status_code == 404
    assert _post(parser, SENIOR, f"/information/suggestions/{sid}/postpone").status_code == 404
    body = {"basis": "responsible"}
    assert _post(parser, SENIOR, f"/information/memes/{meme['id']}/coauthor-requests", body).status_code == 404
    assert _get(parser, SENIOR, f"/information/suggestions/{sid}/prefill").status_code == 404


# --- the two tabs (FR-MS3, FR-MS11, FR-MS15, FR-MS16) ---------------------------------------------------------------


def test_yours_lists_only_own_suggestions_in_sections(parser):
    summary = _get(parser, A, "/information/summary").json()
    # A is a candidate of: m1 #1, m2 #1 (confirmer), m3 #2 (confirmer), c1 #2 (speaker), c1 #3 (confirmer)
    assert summary == {"to_decide": 5, "postponed": 0, "decided": 0, "coauthor": 0, "badge": 5}
    mine = _items(parser, A)
    assert len(mine) == 5 and all(it["type"] == "suggestion" for it in mine)
    assert all(any(s["is_mine"] for s in it["meme"]["suggestions"]) for it in mine)
    assert _items(parser, A, section="postponed") == [] and _items(parser, A, section="decided") == []


def test_meme_appears_in_yours_and_others_but_never_as_own_suggestion_in_others(parser):
    # CUTOFF (m1): A and C are candidates; TL, B and Manager are only participants
    for uid in (A, C):
        assert CUTOFF in _titles(parser, uid)
        others = [i["meme"] for i in _items(parser, uid, "others") if i["meme"]["source"]["title"] == "Payroll BE weekly"]
        assert CUTOFF in {m["title"] for m in others}  # the other candidate's suggestion
    # B is not a candidate of CUTOFF: only in Others
    assert CUTOFF not in {i["meme"]["title"] for sec in SECTIONS for i in _items(parser, B, section=sec)}
    assert CUTOFF in _titles(parser, B, "others")
    # VIES (m1): B is the only candidate -> only Yours for B, Others for the rest
    assert VIES in _titles(parser, B)
    assert VIES not in _titles(parser, B, "others")
    assert VIES in _titles(parser, A, "others")


def test_filters_and_pagination(parser):
    everything = _get(parser, A, "/information", params={"tab": "yours", "page_size": 2}).json()
    assert everything["total"] == 5 and len(everything["items"]) == 2 and everything["page"] == 1
    assert everything["counts"] == {"to_decide": 5, "postponed": 0, "decided": 0, "coauthor": 0}
    page3 = _get(parser, A, "/information", params={"tab": "yours", "page_size": 2, "page": 3}).json()
    assert len(page3["items"]) == 1 and page3["page"] == 3
    # newest source first
    dates = [i["meme"]["source"]["date_from"] for i in _items(parser, A)]
    assert dates == sorted(dates, reverse=True)

    meetings = _get(parser, A, "/information", params={"kind": "meeting", "page_size": 50}).json()
    chats = _get(parser, A, "/information", params={"kind": "chat", "page_size": 50}).json()
    both = _get(parser, A, "/information", params={"kind": ["meeting", "chat"], "page_size": 50}).json()
    assert meetings["total"] == 3 and chats["total"] == 2 and both["total"] == 5
    assert {i["meme"]["source"]["kind"] for i in meetings["items"]} == {"meeting"}
    others = _get(parser, A, "/information", params={"tab": "others", "kind": "chat", "page_size": 50}).json()
    assert {i["meme"]["source"]["kind"] for i in others["items"]} == {"chat"}
    # default page size is 10
    assert _get(parser, A, "/information", params={"tab": "others"}).json()["page_size"] == 10


# --- decisions (FR-MO2 to FR-MO8, FR-MO18 to FR-MO22) ---------------------------------------------------------------


def test_approve_needs_a_basis_and_a_source_when_relayed(parser):
    sid = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    assert _post(parser, C, f"/information/suggestions/{sid}/approve", {}).status_code == 422
    assert _approve(parser, C, sid, "relayed").status_code == 422
    assert _approve(parser, C, sid, "relayed", "   ").status_code == 422
    assert _mine(_meme(parser, C, CUTOFF, "Payroll BE weekly"))["state"] == "pending"
    r = _approve(parser, C, sid, "relayed", "Payroll newsletter, September 2026")
    assert r.status_code == 200
    meme = r.json()["meme"]
    assert meme["status"] == "preparing"  # one approval is enough; A has not decided yet
    mine = _mine(meme)
    assert (mine["state"], mine["label"], mine["basis"]) == ("accepted", "Approved, not yet added", "relayed")
    assert mine["source"] == "Payroll newsletter, September 2026"
    assert [a["user"]["display_name"] for a in meme["authors"]] == ["Employee C"]


def test_only_the_owner_decides(parser):
    meme = _meme(parser, A, CUTOFF, "Payroll BE weekly")
    others_sid = next(s["id"] for s in meme["suggestions"] if not s["is_mine"])
    for action, body in (("approve", {"basis": "responsible"}), ("reject", {}), ("postpone", None),
                         ("reopen", None), ("withdraw", None)):
        r = _post(parser, A, f"/information/suggestions/{others_sid}/{action}", body)
        assert r.status_code == 403, action
    # not the uploader, a manager or an admin either: they are not the owner
    for uid in (MANAGER, TEAM_LEAD, B):
        assert _approve(parser, uid, others_sid).status_code == 403
    assert _mine(_meme(parser, C, CUTOFF, "Payroll BE weekly"))["state"] == "pending"


def test_reject_is_final_and_keeps_its_history(parser):
    sid = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    r = _post(parser, C, f"/information/suggestions/{sid}/reject", {"reason": "I didn't confirm this"})
    assert r.status_code == 200
    mine = _mine(r.json()["meme"])
    assert (mine["state"], mine["label"], mine["reason"]) == ("declined", "Rejected", "I didn't confirm this")
    assert [e["action"] for e in mine["history"]] == ["created", "reject"]
    for action, body in (("approve", {"basis": "responsible"}), ("postpone", None), ("reopen", None)):
        assert _post(parser, C, f"/information/suggestions/{sid}/{action}", body).status_code == 409
    # moved to Decided
    assert CUTOFF not in _titles(parser, C)
    assert CUTOFF in _titles(parser, C, section="decided")
    # a rejection does not change the other candidate's request, and its reason is visible to them
    other = next(s for s in _meme(parser, A, CUTOFF, "Payroll BE weekly")["suggestions"] if not s["is_mine"])
    assert other["state"] == "declined" and other["reason"] == "I didn't confirm this"
    assert _mine(_meme(parser, A, CUTOFF, "Payroll BE weekly"))["state"] == "pending"


def test_postpone_reopen_and_not_declined(parser):
    sa = _sug(parser, A, CUTOFF, "Payroll BE weekly")
    sc = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    assert _post(parser, A, f"/information/suggestions/{sa}/postpone").status_code == 200
    summary = _get(parser, A, "/information/summary").json()
    assert summary["to_decide"] == 4 and summary["postponed"] == 1
    assert CUTOFF in _titles(parser, A, section="postponed")
    assert CUTOFF not in _titles(parser, A)
    # the other candidate rejects: with a postponed suggestion the meme is not Declined
    r = _post(parser, C, f"/information/suggestions/{sc}/reject", {})
    assert r.json()["meme"]["status"] == "new"
    # a postponed suggestion can still be approved...
    meme = _post(parser, A, f"/information/suggestions/{sa}/reopen").json()["meme"]
    assert _mine(meme)["state"] == "pending" and meme["status"] == "new"
    _post(parser, A, f"/information/suggestions/{sa}/postpone")
    assert _approve(parser, A, sa).json()["meme"]["status"] == "preparing"


def test_all_candidates_rejecting_declines_the_meme(parser):
    sa = _sug(parser, A, CUTOFF, "Payroll BE weekly")
    sc = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    _post(parser, A, f"/information/suggestions/{sa}/reject", {})
    r = _post(parser, C, f"/information/suggestions/{sc}/reject", {"reason": "incorrect"})
    assert r.json()["meme"]["status"] == "declined"
    # no longer publishable
    assert _post(parser, B, f"/information/suggestions/{sa}/approve", {"basis": "responsible"}).status_code == 403
    assert _post(parser, A, f"/information/suggestions/{sa}/approve", {"basis": "responsible"}).status_code == 409


def test_withdraw_returns_the_meme_to_new(parser):
    sid = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    assert _post(parser, C, f"/information/suggestions/{sid}/withdraw").status_code == 409  # nothing to withdraw
    _approve(parser, C, sid, "responsible")
    r = _post(parser, C, f"/information/suggestions/{sid}/withdraw")
    assert r.status_code == 200
    meme = r.json()["meme"]
    assert meme["status"] == "new" and _mine(meme)["state"] == "pending" and meme["authors"] == []
    assert [e["action"] for e in _mine(meme)["history"]] == ["created", "approve", "withdraw"]


def test_history_is_append_only_and_visible_to_other_participants(parser, db_session):
    sid = _sug(parser, A, CUTOFF, "Payroll BE weekly")
    _post(parser, A, f"/information/suggestions/{sid}/postpone")
    _post(parser, A, f"/information/suggestions/{sid}/reopen")
    _approve(parser, A, sid, "relayed", "Law X")
    seen_by_b = next(s for s in _meme(parser, B, CUTOFF, tab="others")["suggestions"] if s["id"] == sid)
    assert [e["action"] for e in seen_by_b["history"]] == ["created", "postpone", "reopen", "approve"]
    assert seen_by_b["history"][-1]["basis"] == "relayed" and seen_by_b["history"][-1]["source"] == "Law X"
    assert seen_by_b["state"] == "accepted" and seen_by_b["is_mine"] is False

    from app.models import SuggestionEvent

    row = db_session.query(SuggestionEvent).first()
    row.reason = "tampered"
    with pytest.raises(RuntimeError):
        db_session.commit()
    db_session.rollback()


def test_decisions_are_visible_to_others_right_away_and_postponing_is_silent(parser):
    sa = _sug(parser, A, CUTOFF, "Payroll BE weekly")
    sc = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    _post(parser, A, f"/information/suggestions/{sa}/postpone")

    def notes(uid):
        return [n for n in _get(parser, uid, "/notifications").json() if n["event_type"] == "candidate_decided"]

    assert notes(C) == []  # postponing notifies nobody ...
    other_view = next(s for s in _meme(parser, C, CUTOFF, "Payroll BE weekly")["suggestions"] if s["id"] == sa)
    assert other_view["state"] == "postponed"  # ... but is visible in Others
    _approve(parser, C, sc, "responsible")
    n = notes(A)
    assert len(n) == 1 and "approved" in n[0]["title"] and "tab=others" in n[0]["link"] and f"meme=" in n[0]["link"]


def test_notifications_open_the_right_page(parser):
    notes = _get(parser, A, "/notifications").json()
    assert {"suggestion_received", "memes_ready"} <= {n["event_type"] for n in notes}
    received = next(n for n in notes if n["event_type"] == "suggestion_received")
    assert received["link"].startswith("/information?tab=yours&section=to_decide&suggestion=")
    ready = next(n for n in notes if n["event_type"] == "memes_ready" and "Payroll BE weekly" in n["body"])
    assert "tab=yours" in ready["link"]  # A is a candidate there
    only_participant = [n for n in _get(parser, MANAGER, "/notifications").json()
                        if n["event_type"] == "memes_ready" and "Payroll BE weekly" in n["body"]]
    assert only_participant[0]["link"] == "/information?tab=yours"  # the Manager confirms one meme there

    # Admin took part in c3 as a speaker only; the Manager in several sources: everyone hears "memes ready"
    assert any(n["event_type"] == "memes_ready" for n in _get(parser, MANAGER, "/notifications").json())

    # locate() resolves the link to the tab, section and page that show the item
    assert int(received["link"].rsplit("suggestion=", 1)[1]) in {
        x["id"] for it in _items(parser, A) for x in it["meme"]["suggestions"]
    }
    sid = _sug(parser, A, CUTOFF, "Payroll BE weekly")  # SENIOR took part in other meetings, but not in this one
    loc = _get(parser, A, "/information/locate", params={"suggestion": sid}).json()
    assert loc["tab"] == "yours" and loc["section"] == "to_decide" and loc["page"] == 1
    _post(parser, A, f"/information/suggestions/{sid}/postpone")
    assert _get(parser, A, "/information/locate", params={"suggestion": sid}).json()["section"] == "postponed"
    # a colleague's suggestion leads to the Others tab; a non-participant gets nothing
    other = next(i for i in _items(parser, B, "others") if any(s["id"] == sid for s in i["meme"]["suggestions"]))
    assert other
    loc = _get(parser, B, "/information/locate", params={"suggestion": sid}).json()
    assert loc["tab"] == "others"
    assert _get(parser, SENIOR, "/information/locate", params={"suggestion": sid}).status_code == 404
    assert _get(parser, A, "/information/locate").status_code == 422


# --- publishing (FR-MP, UC-M4) ----------------------------------------------------------------------------------------------


def _publish(client, uid, sid, form, **over):
    body = {
        "title": form["title"], "body": form["body"], "justification": form["justification"],
        "category_id": form["category_id"], "country": form["country"], "scope": form["scope"],
        "keywords": form["keywords"], "basis": form["basis"] or "responsible", "basis_source": form["basis_source"],
        "suggestion_id": sid,
    }
    body.update(over)
    return client.post("/entries", headers=login(client, uid), json=body)


def test_prefill_for_an_approved_suggestion(parser):
    sid = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    assert _get(parser, C, f"/information/suggestions/{sid}/prefill").status_code == 403  # approve first
    _approve(parser, A, _sug(parser, A, CUTOFF, "Payroll BE weekly"), "responsible")
    _approve(parser, C, sid, "relayed", "Payroll newsletter, September 2026")
    form = _get(parser, C, f"/information/suggestions/{sid}/prefill").json()
    assert form["title"] == CUTOFF and form["category_id"] == 1 and form["country"] == "BE"
    assert form["body"].startswith("Contractor invoices received after the 25th")
    assert form["justification"].startswith("From a meeting: Payroll BE weekly, 2026-10-14.")
    assert "Source: Payroll newsletter, September 2026" in form["justification"]
    assert "twelve" not in form["justification"] and "Yes, that's right" not in form["justification"]  # no quotes
    assert {"contractor", "invoice", "cut-off"} <= set(form["keywords"])
    assert form["basis"] == "relayed" and form["already_published"] is False
    assert {(c["owner"]["display_name"], c["state"]) for c in form["candidates"]} == {
        ("Employee A", "accepted"), ("Employee C", "accepted")}
    assert [c["display_name"] for c in form["co_authors"]] == ["Employee A"]
    # only the owner can open it
    assert _get(parser, A, f"/information/suggestions/{sid}/prefill").status_code == 403


def test_publish_records_all_approving_authors_and_closes_the_rest(parser):
    sa = _sug(parser, A, CUTOFF, "Payroll BE weekly")
    sc = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    _approve(parser, C, sc, "relayed", "Payroll newsletter, September 2026")
    _approve(parser, A, sa, "responsible")
    # a third candidate is still undecided: use the other meme where TL decides nothing
    form = _get(parser, C, f"/information/suggestions/{sc}/prefill").json()
    r = _publish(parser, C, sc, form)
    assert r.status_code == 201, r.text
    entry = r.json()
    assert entry["current_version"]["status"] == "Unverified" and entry["author"]["id"] == C
    assert entry["current_version"]["justification"].startswith("From a meeting")

    d = _get(parser, B, f"/entries/{entry['public_id']}").json()
    assert [(c["user"]["display_name"], c["role"], c["basis"]) for c in d["contacts"]] == [
        ("Employee A", "co_author", "responsible"), ("Employee C", "author", "relayed")]
    assert d["contacts"][1]["source"] == "Payroll newsletter, September 2026"
    assert d["origin"]["kind"] == "meeting" and d["origin"]["date_from"] == "2026-10-14"
    assert d["origin"]["meme_id"] is not None and d["origin"]["is_participant"] is True  # B took part

    meme = _meme(parser, A, CUTOFF, "Payroll BE weekly")
    assert meme["status"] == "published" and meme["entry"]["public_id"] == entry["public_id"]
    assert {a["user"]["display_name"] for a in meme["authors"]} == {"Employee A", "Employee C"}
    assert all(a["basis"] for a in meme["authors"]) and meme["is_author"] is True
    # tags of the meme are on the entry
    assert {"cut-off", "invoice"} <= {t["name"] for t in entry["tags"]}
    # authors can neither vote on nor verify it (BR-M3)
    vid = entry["current_version"]["id"]
    assert parser.post(f"/entries/{entry['public_id']}/votes", headers=login(parser, A),
                       json={"used_at": "2026-10-20", "where_ref": "x", "is_correct": True}).status_code == 403
    assert _post(parser, SENIOR, f"/approvals/{vid}/verify").status_code == 200  # a verifier in scope can


def test_first_save_wins_and_pending_suggestions_are_closed(parser):
    sa = _sug(parser, A, CUTOFF, "Payroll BE weekly")
    sc = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    _approve(parser, C, sc)
    _approve(parser, A, sa)
    form_c = _get(parser, C, f"/information/suggestions/{sc}/prefill").json()
    form_a = _get(parser, A, f"/information/suggestions/{sa}/prefill").json()
    assert _publish(parser, C, sc, form_c).status_code == 201
    r = _publish(parser, A, sa, form_a)
    assert r.status_code == 409 and "already published" in r.json()["detail"]
    # A is told instead of getting a form, and sees the entry
    again = _get(parser, A, f"/information/suggestions/{sa}/prefill").json()
    assert again["already_published"] is True and again["entry_public_id"]
    assert _mine(_meme(parser, A, CUTOFF, "Payroll BE weekly"))["label"] == "Approved"


def test_pending_and_postponed_are_closed_on_save_and_notified(parser):
    # c2 (chat): TL speaks, C confirms; the manager is only a participant
    tl = _sug(parser, TEAM_LEAD, CUTOFF, "Contractor payroll — announcements")
    c = _sug(parser, C, CUTOFF, "Contractor payroll — announcements")
    _post(parser, C, f"/information/suggestions/{c}/postpone")
    _approve(parser, TEAM_LEAD, tl)
    form = _get(parser, TEAM_LEAD, f"/information/suggestions/{tl}/prefill").json()
    assert _publish(parser, TEAM_LEAD, tl, form).status_code == 201
    mine = _mine(_meme(parser, C, CUTOFF, "Contractor payroll — announcements"))
    assert (mine["state"], mine["label"]) == ("closed", "Closed: published without you")
    assert mine["history"][-1]["action"] == "closed"
    note = [n for n in _get(parser, C, "/notifications").json() if n["event_type"] == "meme_published"]
    assert len(note) == 1 and "co-authorship" in note[0]["body"]
    assert "section=decided" in note[0]["link"]
    assert CUTOFF in _titles(parser, C, section="decided", source="Contractor payroll — announcements")


def test_only_an_approved_author_can_publish(parser):
    sa = _sug(parser, A, CUTOFF, "Payroll BE weekly")
    sc = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    form = {"title": "t", "body": "b", "justification": None, "category_id": 1, "country": "BE", "scope": "country",
            "keywords": [], "basis": "responsible", "basis_source": None}
    assert _publish(parser, A, sa, form).status_code == 403  # pending, not approved
    _post(parser, A, f"/information/suggestions/{sa}/postpone")
    assert _publish(parser, A, sa, form).status_code == 403
    _approve(parser, A, sa)
    assert _publish(parser, C, sa, form).status_code == 403  # somebody else's suggestion
    assert _publish(parser, SENIOR, sa, form).status_code == 404  # not a participant
    assert _publish(parser, A, 99999, form).status_code == 404
    _post(parser, C, f"/information/suggestions/{sc}/reject", {})
    form_a = _get(parser, A, f"/information/suggestions/{sa}/prefill").json()
    assert _publish(parser, A, sa, form_a).status_code == 201  # a rejection by C does not block A
    d = _get(parser, A, f"/entries/{_meme(parser, A, CUTOFF, 'Payroll BE weekly')['entry']['public_id']}").json()
    assert [c["user"]["display_name"] for c in d["contacts"]] == ["Employee A"]  # C rejected: not an author


def test_sensitive_memes_need_confirmed_clean_text(parser, db_session):
    from app.models import Meme

    sid = _sug(parser, A, CUTOFF, "Payroll BE weekly")
    db_session.query(Meme).filter(Meme.title == CUTOFF, Meme.source_id == 1).update({"sensitive": True})
    db_session.commit()
    db_session.close()
    _approve(parser, A, sid)
    form = _get(parser, A, f"/information/suggestions/{sid}/prefill").json()
    assert form["sensitive"] is True
    r = _publish(parser, A, sid, form)
    assert r.status_code == 422 and "confidential" in r.json()["detail"]
    assert _publish(parser, A, sid, form, sensitive_confirmed=True).status_code == 201


def test_same_information_from_another_source_is_a_separate_meme(parser):
    # CUTOFF exists in m1 (A, C) and c2 (TL, C): C has two separate suggestions; nobody joins across sources
    c_m1 = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    c_c2 = _sug(parser, C, CUTOFF, "Contractor payroll — announcements")
    assert c_m1 != c_c2
    _approve(parser, C, c_m1)
    form = _get(parser, C, f"/information/suggestions/{c_m1}/prefill").json()
    first = _publish(parser, C, c_m1, form).json()
    # the second one is found by the duplicate warning, which lists the first entry
    sim = _get(parser, C, "/entries/similar", params={"title": CUTOFF, "body": form["body"]}).json()
    assert first["public_id"] in {s["public_id"] for s in sim}
    d = _get(parser, A, f"/entries/{first['public_id']}").json()
    assert d["origin"]["is_participant"] is True
    outsider = _get(parser, SENIOR, f"/entries/{first['public_id']}").json()
    assert outsider["origin"]["is_participant"] is False and outsider["origin"]["meme_id"] is None
    # nobody joins across sources: a non-participant of this meeting cannot request co-authorship of it
    mid = _meme(parser, A, CUTOFF, "Payroll BE weekly")["id"]
    assert _post(parser, SENIOR, f"/information/memes/{mid}/coauthor-requests", {"basis": "responsible"}).status_code == 404


# --- co-authorship after publication (UC-M7) -----------------------------------------------------------------------------


@pytest.fixture()
def published(parser):
    """CUTOFF (m1) published by C; A's suggestion was still pending, so it is closed."""
    sc = _sug(parser, C, CUTOFF, "Payroll BE weekly")
    _approve(parser, C, sc, "responsible")
    form = _get(parser, C, f"/information/suggestions/{sc}/prefill").json()
    entry = _publish(parser, C, sc, form).json()
    return parser, entry, _meme(parser, C, CUTOFF, "Payroll BE weekly")["id"]


def _request(client, uid, mid, **over):
    body = {"basis": "responsible", "note": "I said it", "evidence": "00:12:31"}
    body.update(over)
    return client.post(f"/information/memes/{mid}/coauthor-requests", headers=login(client, uid), json=body)


def test_closed_candidate_requests_coauthorship_with_own_quote_as_evidence(published):
    client, entry, mid = published
    meme = _meme(client, A, CUTOFF, "Payroll BE weekly")
    assert meme["can_request_coauthorship"] is True and meme["request_blocked_reason"] is None
    r = _request(client, A, mid, basis="relayed", source="Handbook")
    assert r.status_code == 201, r.text
    req = r.json()["my_request"]
    assert req["status"] == "pending" and req["evidence_quote"]["text"]  # A's own detected quote
    assert req["basis"] == "relayed" and req["source"] == "Handbook" and req["note"] == "I said it"
    # one open request per person
    assert _request(client, A, mid).status_code == 409
    assert "open request" in _meme(client, A, CUTOFF, "Payroll BE weekly")["request_blocked_reason"]
    # C, the author, finds it in Yours -> Co-author requests and in the badge
    assert _get(client, C, "/information/summary").json()["coauthor"] == 1
    items = _items(client, C, section="coauthor")
    assert len(items) == 1 and items[0]["type"] == "coauthor_request"
    assert items[0]["request"]["requester"]["display_name"] == "Employee A"
    notes = [n for n in _get(client, C, "/notifications").json() if n["event_type"] == "coauthor_requested"]
    assert len(notes) == 1 and "section=coauthor" in notes[0]["link"] and "request=" in notes[0]["link"]
    loc = _get(client, C, "/information/locate", params={"request": items[0]["id"]}).json()
    assert (loc["tab"], loc["section"]) == ("yours", "coauthor")


def test_accepting_makes_a_coauthor_without_a_new_version(published):
    client, entry, mid = published
    vid = entry["current_version"]["id"]
    _post(client, SENIOR, f"/approvals/{vid}/verify")  # the entry is verified before the co-author joins
    _request(client, A, mid, basis="responsible")
    rid = _items(client, C, section="coauthor")[0]["id"]
    r = _post(client, C, f"/information/coauthor-requests/{rid}/accept", {"reason": None})
    assert r.status_code == 200 and r.json()["request"]["status"] == "accepted"
    assert r.json()["request"]["decided_by"]["display_name"] == "Employee C"

    d = _get(client, B, f"/entries/{entry['public_id']}").json()
    assert d["current_version"]["version_number"] == 1 and d["current_version"]["status"] == "Verified"
    assert {(c["user"]["display_name"], c["role"]) for c in d["contacts"]} == {
        ("Employee A", "co_author"), ("Employee C", "author")}
    # the contributors list shows the co-author without any line of text
    contrib = _get(client, B, f"/entries/{entry['public_id']}/contributors").json()
    mine = next(c for c in contrib["contributors"] if c["user"]["display_name"] == "Employee A")
    assert mine["fragment_count"] == 0 and mine["fragment_indexes"] == []
    # A is an author now: badge, Contacts and Responsibilities tab
    meme = _meme(client, A, CUTOFF, "Payroll BE weekly")
    assert meme["is_author"] is True and {a["user"]["display_name"] for a in meme["authors"]} == {"Employee A", "Employee C"}
    resp = _get(client, B, f"/people/{A}/responsibilities").json()
    assert entry["public_id"] in {i["public_id"] for i in resp["responsible"]}
    assert [i["role"] for i in resp["responsible"] if i["public_id"] == entry["public_id"]] == ["co_author"]
    notes = [n for n in _get(client, A, "/notifications").json() if n["event_type"] == "coauthor_decided"]
    assert len(notes) == 1 and notes[0]["link"] == f"/entries/{entry['public_id']}"
    # no longer allowed to vote or verify
    assert client.post(f"/entries/{entry['public_id']}/votes", headers=login(client, A),
                       json={"used_at": "2026-10-20", "where_ref": "x", "is_correct": True}).status_code == 403
    # A's own item in Decided shows A as an author, with the join in the history
    item = next(i for i in _items(client, A, section="decided") if i["type"] == "suggestion")
    assert item["meme"]["is_author"] is True
    assert item["meme"]["suggestions"][0]["history"][-1]["action"] == "joined"


def test_first_author_to_answer_decides(parser):
    # c2: TL speaks, C confirms; both approve; TL publishes; the manager (participant) asks to join
    tl = _sug(parser, TEAM_LEAD, CUTOFF, "Contractor payroll — announcements")
    c = _sug(parser, C, CUTOFF, "Contractor payroll — announcements")
    _approve(parser, TEAM_LEAD, tl)
    _approve(parser, C, c, "relayed", "Newsletter")
    form = _get(parser, TEAM_LEAD, f"/information/suggestions/{tl}/prefill").json()
    assert _publish(parser, TEAM_LEAD, tl, form).status_code == 201
    mid = _meme(parser, MANAGER, CUTOFF, "Contractor payroll — announcements", tab="others")["id"]
    assert _request(parser, MANAGER, mid).status_code == 201
    for uid in (TEAM_LEAD, C):  # both authors see it
        assert len(_items(parser, uid, section="coauthor")) == 1
    rid = _items(parser, TEAM_LEAD, section="coauthor")[0]["id"]
    assert _post(parser, SENIOR, f"/information/coauthor-requests/{rid}/accept", {}).status_code == 404  # no participant
    assert _post(parser, MANAGER, f"/information/coauthor-requests/{rid}/accept", {}).status_code == 403  # not an author
    assert _post(parser, TEAM_LEAD, f"/information/coauthor-requests/{rid}/decline", {"reason": "not yours"}).status_code == 200
    # the other author can no longer decide; the request left their list and shows who decided
    r = _post(parser, C, f"/information/coauthor-requests/{rid}/accept", {})
    assert r.status_code == 409 and "Team Lead" in r.json()["detail"]
    assert _items(parser, C, section="coauthor") == []
    decided = [i for i in _items(parser, C, section="decided") if i["type"] == "coauthor_request"]
    assert len(decided) == 1 and decided[0]["request"]["decided_by"]["display_name"] == "Team Lead"
    assert decided[0]["request"]["status"] == "declined" and decided[0]["request"]["decision_reason"] == "not yours"
    # a declined request cannot be repeated
    again = _request(parser, MANAGER, mid)
    assert again.status_code == 409 and "declined" in again.json()["detail"]
    # the decline is visible to the requester as a notification that opens the item in Others
    note = [n for n in _get(parser, MANAGER, "/notifications").json() if n["event_type"] == "coauthor_decided"]
    assert len(note) == 1 and "tab=others" in note[0]["link"]


def test_request_is_blocked_by_usage_vote_or_verification(published, db_session):
    client, entry, mid = published
    pid = entry["public_id"]
    # B voted on the entry: must withdraw first
    r = client.post(f"/entries/{pid}/votes", headers=login(client, B),
                    json={"used_at": "2026-10-20", "where_ref": "case 1", "is_correct": True})
    assert r.status_code in (200, 201), r.text
    reason = _meme(client, B, CUTOFF, "Payroll BE weekly", tab="others")["request_blocked_reason"]
    assert "usage vote" in reason
    assert _request(client, B, mid).status_code == 409
    vote_id = r.json()["id"]
    assert client.delete(f"/entries/{pid}/votes/{vote_id}", headers=login(client, B)).status_code in (200, 204)
    assert _request(client, B, mid).status_code == 201
    # a verifier of the current version cannot request (TL verified, TL is a participant of m1)
    vid = entry["current_version"]["id"]
    assert _post(client, TEAM_LEAD, f"/approvals/{vid}/verify").status_code == 200
    reason = _meme(client, TEAM_LEAD, CUTOFF, "Payroll BE weekly", tab="others")["request_blocked_reason"]
    assert "verified" in reason
    assert _request(client, TEAM_LEAD, mid).status_code == 409


def test_authors_and_unpublished_memes_cannot_request(parser, published):
    client, entry, mid = published
    assert _request(client, C, mid).status_code == 409  # C is an author
    unpublished = _meme(client, A, VIES, tab="others")["id"]
    assert _request(client, A, unpublished).status_code == 409
    assert _request(client, A, mid, basis="relayed").status_code == 422  # relayed needs a source


def test_entry_page_origin_and_notice_for_authors(published):
    client, entry, mid = published
    pid = entry["public_id"]
    assert _get(client, C, f"/entries/{pid}").json()["origin"]["pending_requests"] == 0
    _request(client, A, mid)
    author_view = _get(client, C, f"/entries/{pid}").json()["origin"]
    assert author_view["pending_requests"] == 1 and author_view["is_author"] is True
    a_view = _get(client, A, f"/entries/{pid}").json()["origin"]
    assert a_view["can_request_coauthorship"] is True and a_view["my_request_status"] == "pending"
    # a non-participant sees only the origin line, nothing of the conversation
    senior = _get(client, SENIOR, f"/entries/{pid}").json()["origin"]
    assert senior == {"kind": "meeting", "date_from": "2026-10-14", "date_to": None, "is_participant": False, "meme_id": None}


# --- retention (BR-M7) -------------------------------------------------------------------------------------------------------


def test_raw_sources_are_purged_after_retention_but_memes_stay(parser, db_session):
    from datetime import datetime, timedelta

    from app.models import Meme, Quote, Source
    from app.services.parser_agent import purge_expired_sources

    sources = db_session.query(Source).all()
    assert all(s.raw_ref and s.raw_expires_at > datetime.utcnow() + timedelta(days=29) for s in sources)
    assert purge_expired_sources(db_session) == 0
    memes, quotes = db_session.query(Meme).count(), db_session.query(Quote).count()
    assert purge_expired_sources(db_session, now=datetime.utcnow() + timedelta(days=31)) == 6
    assert all(s.raw_ref is None and s.raw_purged_at for s in db_session.query(Source))
    assert (db_session.query(Meme).count(), db_session.query(Quote).count()) == (memes, quotes)
    assert purge_expired_sources(db_session, now=datetime.utcnow() + timedelta(days=60)) == 0  # idempotent


def test_import_is_idempotent_and_admins_cannot_read_foreign_conversations(parser, db_session):
    from app.services.parser_agent import load_mock_sources

    assert load_mock_sources(db_session) == 0
    # Admin only took part in c3: nothing of m1 or c1 is visible to them
    titles = {it["meme"]["source"]["title"] for tab in ("yours", "others") for sec in SECTIONS
              for it in _items(parser, ADMIN, tab, sec)}
    assert titles == {"Freelance onboarding — cross-team"}


# --- agent settings and hardening (iteration 24) -------------------------------------------------------------------------


def test_agent_settings_are_admin_only_and_validated(parser):
    keys = {s["key"] for s in _get(parser, ADMIN, "/admin/settings").json()}
    assert {"parser_confidence_threshold", "parser_raw_retention_days"} <= keys
    assert "parser_useful_vote_threshold" not in keys  # usefulness votes are gone

    def put(uid, key, value):
        return parser.put(f"/admin/settings/{key}", params={"value": value}, headers=login(parser, uid))

    assert put(A, "parser_confidence_threshold", "0.7").status_code == 403
    assert put(ADMIN, "parser_confidence_threshold", "0.7").status_code == 200
    assert put(ADMIN, "parser_confidence_threshold", "1.5").status_code == 422
    assert put(ADMIN, "parser_confidence_threshold", "high").status_code == 422
    assert put(ADMIN, "parser_raw_retention_days", "7").status_code == 200


def test_my_contributions_lists_coauthored_entries(published):
    client, entry, mid = published
    _request(client, A, mid)
    rid = _items(client, C, section="coauthor")[0]["id"]
    _post(client, C, f"/information/coauthor-requests/{rid}/accept", {})
    mine = _get(client, A, "/me/contributions").json()
    assert [e["public_id"] for e in mine["co_authored"]] == [entry["public_id"]]
    assert mine["co_authored"][0]["author"]["display_name"] == "Employee C"
    assert entry["public_id"] not in {e["public_id"] for e in mine["entries"]}  # not the author


# --- no likes or dislikes ---------------------------------------------------------------------------------------------------


def test_there_are_no_usefulness_votes(parser):
    meme = _meme(parser, B, CUTOFF, tab="others")
    assert "votes" not in meme
    for method in (parser.put, parser.delete):
        r = method(f"/information/memes/{meme['id']}/vote", headers=login(parser, B), **({"json": {"useful": True}} if method == parser.put else {}))
        assert r.status_code in (404, 405)
    assert not [n for n in _get(parser, A, "/notifications").json() if n["event_type"] == "useful_threshold"]


def test_meme_detail_lists_pending_requests_for_authors(published):
    client, entry, mid = published
    _request(client, A, mid)
    detail = _get(client, C, f"/information/memes/{mid}").json()
    assert [r["requester"]["display_name"] for r in detail["pending_requests"]] == ["Employee A"]
    assert _get(client, B, f"/information/memes/{mid}").json()["pending_requests"] == []  # only authors see them
