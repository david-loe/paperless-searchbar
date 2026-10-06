import json

import pytest
from conftest import login
from searchbar.db import SearchConfiguration


def test_configuration_is_admin_only_and_persistent(env):
    app, client, _ = env
    login(client)
    for path in ("/api/admin/filters", "/api/admin/search-settings"):
        assert client.get(path).status_code == 403
    assert (
        client.put("/api/admin/search-settings", json={"custom_field_ids": []}).status_code == 403
    )
    login(client, admin=True)
    response = client.put("/api/admin/search-settings", json={"custom_field_ids": [5, 3]})
    assert response.status_code == 200
    assert client.get("/api/admin/search-settings").json() == {"custom_field_ids": [5, 3]}
    with app.state.db() as db:
        assert db.get(SearchConfiguration, 1).custom_field_ids == [5, 3]
    assert len(client.get("/api/admin/filters").json()["custom_fields"]) == 10
    assert [f["id"] for f in client.get("/api/filters").json()["custom_fields"]] == [5, 3]
    login(client)
    fields = client.get("/api/filters").json()["custom_fields"]
    assert [f["id"] for f in fields] == [5, 3]
    assert all(f["operators"] == ["exact"] for f in fields)
    assert fields[0]["options"] == [{"id": "a", "label": "Allgemein"}]
    # The hidden Mandant field must still constrain permissions.
    assert client.post("/api/documents/search", json={"storage_path": 1}).json()["count"] == 1


@pytest.mark.parametrize("ids", [[999], [1, 1], list(range(1, 10)), ["1"]])
def test_invalid_settings_do_not_replace_configuration(env, ids):
    _, client, _ = env
    login(client, admin=True)
    assert (
        client.put("/api/admin/search-settings", json={"custom_field_ids": ids}).status_code == 422
    )
    assert client.get("/api/admin/search-settings").json()["custom_field_ids"] == [1, 5]


@pytest.mark.parametrize("op", ["icontains", "in", "exists", "empty", "range", "contains"])
def test_search_rejects_non_exact_operators(env, op):
    _, client, _ = env
    login(client)
    response = client.post(
        "/api/documents/search", json={"custom_fields": [{"field": 1, "op": op, "value": "A"}]}
    )
    assert response.status_code == 422


def test_exact_search_and_disabled_fields(env):
    _, client, fake = env
    login(client, admin=True)
    for value, count in [("A", 1), ("a", 0), ("", 0)]:
        response = client.post(
            "/api/documents/search", json={"custom_fields": [{"field": 1, "value": value}]}
        )
        assert response.status_code == 200
        assert response.json()["count"] == count
        assert json.loads(fake.calls[-1].url.params["custom_field_query"]) == [
            "AND",
            [[1, "exact", value]],
        ]
    assert (
        client.put("/api/admin/search-settings", json={"custom_field_ids": []}).status_code == 200
    )
    assert client.get("/api/filters").json()["custom_fields"] == []
    assert (
        client.post(
            "/api/documents/search", json={"custom_fields": [{"field": 1, "value": "A"}]}
        ).status_code
        == 422
    )
    assert client.post("/api/documents/search", json={"document_id": 101}).json()["count"] == 1


def test_fresh_install_and_deleted_search_field(env):
    app, client, fake = env
    clock = [0]
    app.state.paperless.catalog_cache.clock = lambda: clock[0]
    with app.state.db() as db:
        db.delete(db.get(SearchConfiguration, 1))
        db.commit()
    login(client, admin=True)
    assert client.get("/api/admin/search-settings").json() == {"custom_field_ids": []}
    assert (
        client.put("/api/admin/search-settings", json={"custom_field_ids": [5]}).status_code == 200
    )
    fake.catalog["custom_fields"] = [f for f in fake.catalog["custom_fields"] if f["id"] != 5]
    assert client.get("/api/filters").json()["custom_fields"][0]["id"] == 5
    clock[0] = 300
    assert client.get("/api/filters").json()["custom_fields"] == []
    response = client.post(
        "/api/documents/search", json={"custom_fields": [{"field": 5, "value": "a"}]}
    )
    assert response.status_code == 422
