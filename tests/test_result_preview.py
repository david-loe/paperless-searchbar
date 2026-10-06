import json

import pytest
from conftest import example_thumbnail, login


def test_document_type_search_and_scoped_catalog(env):
    _, client, fake = env
    login(client)
    assert client.get("/api/filters").json()["document_types"] == [{"id": 1, "name": "Rechnung"}]
    result = client.post("/api/documents/search", json={"document_type": 1})
    assert result.status_code == 200
    assert result.json()["count"] == 1
    assert result.json()["results"][0]["document_type"] == "Rechnung"
    assert client.get("/api/documents/101").json()["document_type"] == "Rechnung"
    # Filters remain intersected with each other and with the hidden permission rule.
    client.post(
        "/api/documents/search", json={"document_type": 1, "storage_path": 1, "correspondent": 1}
    )
    params = fake.calls[-1].url.params
    assert params["document_type__id__in"] == "1"
    assert params["storage_path__id__in"] == "1"
    assert params["correspondent__id__in"] == "1"
    assert json.loads(params["custom_field_query"]) == ["AND", [[1, "exact", "A"]]]
    for payload in (
        {"document_type": 2},
        {"document_type": 999},
        {"document_type": 1, "storage_path": 2},
    ):
        assert client.post("/api/documents/search", json=payload).json() == {
            "count": 0,
            "results": [],
        }
    login(client, admin=True)
    assert len(client.get("/api/admin/filters").json()["document_types"]) == 2
    assert client.get("/api/documents/303").json()["document_type"] is None


@pytest.mark.parametrize("value", [0, -1, "1", True])
def test_invalid_document_type(env, value):
    _, client, _ = env
    login(client)
    assert client.post("/api/documents/search", json={"document_type": value}).status_code == 422


@pytest.mark.parametrize(
    "content_type,extension",
    [("image/png", ".png"), ("image/webp", ".webp"), ("image/jpeg", ".jpg")],
)
def test_thumbnail_stream_and_headers(env, content_type, extension):
    _, client, fake = env
    assert client.get("/api/documents/101/thumb").status_code == 401
    assert not fake.calls
    login(client)
    fake.thumbnail_content_type = content_type
    response = client.get("/api/documents/101/thumb")
    assert response.status_code == 200
    assert response.content == example_thumbnail()
    assert response.headers["content-type"] == content_type
    assert response.headers["content-disposition"] == f'inline; filename="document-101{extension}"'
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert fake.calls[-1].url.path == "/api/documents/101/thumb/"


@pytest.mark.parametrize("content_type", ["text/html", "image/svg+xml", "application/pdf"])
def test_thumbnail_rejects_unexpected_content(env, content_type):
    _, client, fake = env
    login(client)
    fake.thumbnail_content_type = content_type
    response = client.get("/api/documents/101/thumb")
    assert response.status_code == 502
    assert not response.content.startswith(b"\x89PNG")


@pytest.mark.parametrize("status,expected", [(404, 404), (403, 502), (500, 502)])
def test_thumbnail_errors_do_not_break_document_access(env, status, expected):
    _, client, fake = env
    login(client)
    fake.thumbnail_status = status
    assert client.get("/api/documents/101/thumb").status_code == expected
    assert client.get("/api/documents/101").status_code == 200
