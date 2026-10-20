from datetime import date, timedelta

from tests.conftest import login


def _create(client, user_id, title, country="BE", scope="country", body="Some body text"):
    r = client.post(
        "/entries",
        headers=login(client, user_id),
        json={
            "title": title,
            "body": body,
            "category_id": 1,
            "country": country,
            "scope": scope,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _ids(client, params=None, user_id=1):
    r = client.get("/search", params=params or {}, headers=login(client, user_id))
    assert r.status_code == 200, r.text
    return [e["public_id"] for e in r.json()]


def _facet_id(client, kind, name):
    facets = client.get("/search/facets", headers=login(client, 1)).json()
    return next(x["id"] for x in facets[kind] if x["name"] == name)


def _setup(client):
    e2 = _create(client, 2, "Travel rules for contractors", country="BE", scope="eu")
    e3 = _create(client, 3, "Dutch holiday pay", country="NL", scope="universal")
    return e2["public_id"], e3["public_id"]


def test_no_filters_returns_everything(client):
    e2, e3 = _setup(client)
    assert set(_ids(client)) == {"PP-BE-FRE-00001", e2, e3}


def test_country_filter_or_within_one_filter(client):
    e2, e3 = _setup(client)
    assert set(_ids(client, {"country": "NL"})) == {e3}
    assert set(_ids(client, {"country": ["BE", "NL"]})) == {"PP-BE-FRE-00001", e2, e3}


def test_filters_combine_with_and(client):
    e2, e3 = _setup(client)
    assert _ids(client, {"country": "BE", "scope": "eu"}) == [e2]
    assert _ids(client, {"country": "NL", "scope": "eu"}) == []


def test_scope_filter_matches_seed_and_api_spelling(client):
    e2, e3 = _setup(client)
    # seed entry stores "country-specific", API-created ones store "country"
    assert _ids(client, {"scope": "country"}) == ["PP-BE-FRE-00001"]
    assert set(_ids(client, {"scope": ["eu", "universal"]})) == {e2, e3}


def test_status_and_verifier_role_filters(client):
    e2, e3 = _setup(client)
    detail = client.get(f"/entries/{e2}", headers=login(client, 2)).json()
    version_id = detail["versions"][-1]["id"]
    ok = client.post(f"/approvals/{version_id}/verify", headers=login(client, 4))
    assert ok.status_code == 200, ok.text

    assert _ids(client, {"status": "verified"}) == [e2]
    assert set(_ids(client, {"status": "unverified"})) == {"PP-BE-FRE-00001", e3}
    assert _ids(client, {"verifier_role": "Senior Expert"}) == [e2]
    assert _ids(client, {"verifier_role": "Manager"}) == []
    assert _ids(client, {"status": "outdated"}) == []


def test_author_team_and_project_filters(client):
    e2, e3 = _setup(client)
    assert _ids(client, {"author": 3}) == [e3]
    assert set(_ids(client, {"author": [2, 3]})) == {e2, e3}

    experts = _facet_id(client, "teams", "Payroll Experts")  # Employee A and B
    assert set(_ids(client, {"team": experts})) == {"PP-BE-FRE-00001", e2}

    review = _facet_id(client, "projects", "Quarterly Compliance Review")  # B and C
    assert set(_ids(client, {"project": review})) == {e2, e3}


def test_filters_narrow_without_changing_order(client):
    e2, e3 = _setup(client)
    all_ids = _ids(client)
    narrowed = _ids(client, {"country": ["BE"]})
    assert narrowed == [i for i in all_ids if i in narrowed]


def test_filters_work_without_query_and_with_query(client):
    e2, e3 = _setup(client)
    assert _ids(client, {"department": "Payroll", "country": "NL"}) == [e3]
    assert _ids(client, {"q": "travel", "country": "BE"}) == [e2]
    assert _ids(client, {"q": "travel", "country": "NL"}) == []


def test_updated_date_range(client):
    _setup(client)
    today = date.today()
    tomorrow = today + timedelta(days=1)
    assert len(_ids(client, {"updated_from": today.isoformat(), "updated_to": tomorrow.isoformat()})) == 3
    assert _ids(client, {"updated_from": tomorrow.isoformat()}) == []
    assert _ids(client, {"updated_to": (today - timedelta(days=2)).isoformat()}) == []


def test_facets_endpoint(client):
    _setup(client)
    facets = client.get("/search/facets", headers=login(client, 1)).json()
    assert {"BE", "NL"} <= set(facets["countries"])
    assert "Payroll" in facets["departments"]
    assert "Freelance / contractor payroll" in facets["categories"]
    assert {s["value"] for s in facets["statuses"]} == {"unverified", "verified", "outdated"}
    assert {s["value"] for s in facets["scopes"]} == {"country", "eu", "universal"}
    assert facets["verifier_roles"] == ["Manager", "Team Lead", "Senior Expert"]
    assert {"Employee A", "Employee B", "Employee C"} <= {a["name"] for a in facets["authors"]}
    assert "Payroll Experts" in {t["name"] for t in facets["teams"]}
    assert "Freelancer DMFA Automation" in {p["name"] for p in facets["projects"]}
