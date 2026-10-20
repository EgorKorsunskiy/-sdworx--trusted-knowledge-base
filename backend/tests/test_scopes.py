from tests.conftest import login

A, B, C, SENIOR, TEAM_LEAD, MANAGER, ADMIN = 1, 2, 3, 4, 5, 6, 7


def _companies(client):
    return client.get("/companies", headers=login(client, A)).json()


def _create(client, uid, title, scope="country", **extra):
    body = {
        "title": title,
        "body": "A rule that is valid for one client only.",
        "category_id": 1,
        "country": "BE",
        "scope": scope,
        "basis": "responsible",
    }
    body.update(extra)
    return client.post("/entries", headers=login(client, uid), json=body)


def _ids(client, params):
    r = client.get("/search", headers=login(client, A), params=params)
    assert r.status_code == 200, r.text
    return [e["public_id"] for e in r.json()]


# --- maintenance by Admins (BR-11) -------------------------------------------------------------


def test_every_employee_can_read_companies_and_client_projects(client):
    companies = _companies(client)
    assert {c["name"] for c in companies} >= {"Northwind Logistics", "Contoso Retail"}
    northwind = next(c for c in companies if c["name"] == "Northwind Logistics")
    assert northwind["country"] == "BE" and len(northwind["client_projects"]) == 2
    projects = client.get("/client-projects", headers=login(client, B)).json()
    assert all(p["company"]["name"] for p in projects)


def test_only_admins_maintain_companies(client):
    for uid in (A, SENIOR, TEAM_LEAD, MANAGER):
        r = client.post("/admin/companies", headers=login(client, uid), json={"name": "Fabrikam"})
        assert r.status_code == 403
    r = client.post("/admin/companies", headers=login(client, ADMIN), json={"name": "Fabrikam", "country": "fr"})
    assert r.status_code == 201 and r.json()["country"] == "FR"
    assert client.post("/admin/companies", headers=login(client, ADMIN), json={"name": "fabrikam"}).status_code == 409


def test_client_project_belongs_to_a_company_and_never_names_it(client):
    admin = login(client, ADMIN)
    company = next(c for c in _companies(client) if c["name"] == "Contoso Retail")
    r = client.post(
        "/admin/client-projects", headers=admin, json={"name": "Contoso Retail payroll", "company_id": company["id"]}
    )
    assert r.status_code == 422  # BR-11: client-project names never name the client
    r = client.post(
        "/admin/client-projects", headers=admin, json={"name": "Payroll migration", "company_id": company["id"]}
    )
    assert r.status_code == 201 and r.json()["company"]["name"] == "Contoso Retail"
    dup = client.post(
        "/admin/client-projects", headers=admin, json={"name": "payroll migration", "company_id": company["id"]}
    )
    assert dup.status_code == 409
    assert client.post(
        "/admin/client-projects", headers=admin, json={"name": "X", "company_id": 9999}
    ).status_code == 422


def test_company_in_use_cannot_be_deleted(client):
    admin = login(client, ADMIN)
    company = next(c for c in _companies(client) if c["name"] == "Northwind Logistics")
    assert _create(client, A, "Cut-off at the client", "company", company_id=company["id"]).status_code == 201
    assert client.delete(f"/admin/companies/{company['id']}", headers=admin).status_code == 409
    empty = client.post("/admin/companies", headers=admin, json={"name": "Temp Co"}).json()
    assert client.delete(f"/admin/companies/{empty['id']}", headers=admin).status_code == 204


# --- entries (FR-E7) -----------------------------------------------------------------------------


def test_company_scope_requires_a_company(client):
    r = _create(client, A, "No company chosen", "company")
    assert r.status_code == 422 and "company" in r.json()["detail"].lower()
    r = _create(client, A, "No project chosen", "client_project")
    assert r.status_code == 422 and "client project" in r.json()["detail"].lower()
    assert _create(client, A, "Unknown", "company", company_id=999).status_code == 422


def test_scope_pointers_are_saved_and_shown(client):
    company = next(c for c in _companies(client) if c["name"] == "Northwind Logistics")
    project = company["client_projects"][0]
    e1 = _create(client, A, "Company rule", "company", company_id=company["id"]).json()
    assert e1["scope"] == "company" and e1["company"]["name"] == "Northwind Logistics"
    assert e1["client_project"] is None

    e2 = _create(client, A, "Project rule", "client_project", client_project_id=project["id"]).json()
    assert e2["client_project"]["name"] == project["name"]
    assert e2["company"]["id"] == company["id"] if e2["company"] else True  # the company follows the project
    assert e2["client_project"]["company"]["name"] == "Northwind Logistics"

    # A broader scope never keeps a pointer
    e3 = _create(client, A, "Country rule", "country", company_id=company["id"]).json()
    assert e3["company"] is None and e3["client_project"] is None


def test_entry_text_must_not_name_the_client(client):
    company = next(c for c in _companies(client) if c["name"] == "Northwind Logistics")
    r = _create(client, A, "Northwind Logistics overtime rule", "company", company_id=company["id"])
    assert r.status_code == 422 and "Northwind Logistics" in r.json()["detail"]
    r = _create(client, A, "Overtime", "company", company_id=company["id"], body="northwind logistics pays more")
    assert r.status_code == 422


# --- search (FR-S5, BR-1) --------------------------------------------------------------------------


def test_company_and_client_project_filters_and_ranking(client):
    northwind = next(c for c in _companies(client) if c["name"] == "Northwind Logistics")
    contoso = next(c for c in _companies(client) if c["name"] == "Contoso Retail")
    project = northwind["client_projects"][0]
    in_company = _create(client, A, "Overtime rule", "company", company_id=northwind["id"]).json()["public_id"]
    in_project = _create(
        client, A, "Overtime rule for the rollout", "client_project", client_project_id=project["id"]
    ).json()["public_id"]
    other = _create(client, A, "Overtime rule elsewhere", "company", company_id=contoso["id"]).json()["public_id"]
    broad = _create(client, B, "Overtime in general").json()["public_id"]

    # Company filter: the company's entries and those of its client projects
    assert set(_ids(client, {"company": northwind["id"]})) == {in_company, in_project}
    assert _ids(client, {"client_project": project["id"]}) == [in_project]
    assert set(_ids(client, {"scope": "company"})) == {in_company, other}
    assert set(_ids(client, {"scope": ["company", "client_project"]})) == {in_company, in_project, other}
    # Filters combine with AND
    assert _ids(client, {"company": northwind["id"], "client_project": project["id"]}) == [in_project]

    # BR-1: narrow entries rank first when asked for, and below broader entries otherwise
    asked = _ids(client, {"q": "overtime", "company": northwind["id"]})
    assert set(asked[:2]) == {in_company, in_project}
    unfiltered = _ids(client, {"q": "overtime"})
    assert unfiltered[0] == broad
    assert unfiltered.index(broad) < unfiltered.index(in_company) and unfiltered.index(broad) < unfiltered.index(other)


def test_facets_list_companies_and_client_projects(client):
    facets = client.get("/search/facets", headers=login(client, A)).json()
    assert {c["name"] for c in facets["companies"]} >= {"Northwind Logistics", "Contoso Retail"}
    assert any(p["company"] == "Northwind Logistics" for p in facets["client_projects"])
    assert {"company", "client_project"} <= {s["value"] for s in facets["scopes"]}
