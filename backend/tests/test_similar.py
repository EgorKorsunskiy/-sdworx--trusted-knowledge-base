from tests.conftest import login

SEED_TITLE = "Belgian freelancer DMFA filing deadline"
SEED_BODY = (
    "Freelancers in Belgium must be reported to the DMFA at least once per quarter, "
    "via the client's payroll provider or social secretariat."
)


def test_similar_requires_sign_in(client):
    r = client.get("/entries/similar", params={"title": SEED_TITLE, "body": SEED_BODY})
    assert r.status_code == 401


def test_similar_finds_the_duplicate_and_is_not_shadowed_by_entry_lookup(client):
    r = client.get("/entries/similar", params={"title": SEED_TITLE, "body": SEED_BODY}, headers=login(client, 2))
    assert r.status_code == 200, r.text  # used to answer 404 "Entry not found" from /entries/{public_id}
    matches = r.json()
    assert [m["public_id"] for m in matches] == ["PP-BE-FRE-00001"]
    assert matches[0]["score"] >= 0.6


def test_similar_ignores_unrelated_text(client):
    r = client.get(
        "/entries/similar",
        params={"title": "Office plant watering rota", "body": "Water the ficus on Mondays and Thursdays."},
        headers=login(client, 2),
    )
    assert r.status_code == 200 and r.json() == []
