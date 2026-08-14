"""The combined ASGI application.

Falls through to Flask for every route not yet moved, serves the
generated OpenAPI document, admits the tokens Flask's /login issues, and
answers errors with the {"error": ...} envelope the frontend parses.
"""


def test_flask_routes_fall_through(asgi_client, client, seeded):
    via_asgi = asgi_client.get("/seasons")
    via_flask = client.get("/seasons")
    assert via_asgi.status_code == via_flask.status_code == 200
    assert via_asgi.json() == via_flask.get_json()


def test_unknown_path_falls_through_to_flask(asgi_client, client):
    assert asgi_client.get("/no-such-path").status_code == 404
    assert client.get("/no-such-path").status_code == 404


def test_flasgger_spec_still_serves(asgi_client):
    spec = asgi_client.get("/apispec.json")
    assert spec.status_code == 200
    assert spec.json()["swagger"] == "2.0"


def test_openapi_document_serves(asgi_client):
    doc = asgi_client.get("/openapi.json")
    assert doc.status_code == 200
    assert doc.json()["info"]["title"] == "GNL Backend API"


def test_docs_page_serves(asgi_client):
    assert asgi_client.get("/docs").status_code == 200


def test_access_token_admits(probe_client, auth_headers):
    resp = probe_client.get("/guarded", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"identity": "admin"}


def test_refresh_token_is_rejected(probe_client, refresh_headers):
    resp = probe_client.get("/guarded", headers=refresh_headers)
    assert resp.status_code == 401
    assert resp.json() == {"msg": "Only non-refresh tokens are allowed"}


def test_missing_header_is_rejected(probe_client):
    resp = probe_client.get("/guarded")
    assert resp.status_code == 401
    assert resp.json() == {"msg": "Missing Authorization Header"}


def test_forged_token_is_rejected(probe_client):
    resp = probe_client.get("/guarded", headers={"Authorization": "Bearer forged"})
    assert resp.status_code == 401


def test_not_found_answers_404_with_error_envelope(probe_client):
    resp = probe_client.get("/missing")
    assert resp.status_code == 404
    assert resp.json() == {"error": "NotFoundException: nothing here"}


def test_db_exception_answers_500_with_error_envelope(probe_client):
    resp = probe_client.get("/db-broken")
    assert resp.status_code == 500
    assert resp.json() == {"error": "DBException: db says no"}


def test_unhandled_exception_answers_500_with_error_envelope(probe_client):
    resp = probe_client.get("/broken")
    assert resp.status_code == 500
    assert resp.json() == {"error": "boom"}
