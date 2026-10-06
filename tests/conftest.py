import copy
import json
import struct
import zlib

import httpx
import pytest
from fastapi.testclient import TestClient
from searchbar.app import create_app
from searchbar.config import Settings
from searchbar.db import Base, GuestCode, Profile, SearchConfiguration, User, now
from searchbar.schemas import Rules
from searchbar.security import digest

CATALOG = {
    "storage_paths": [{"id": 1, "name": "Buchhaltung"}, {"id": 2, "name": "Privat"}],
    "correspondents": [{"id": 1, "name": "Firma A"}, {"id": 2, "name": "Firma B"}],
    "document_types": [{"id": 1, "name": "Rechnung"}, {"id": 2, "name": "Vertrag"}],
    "custom_fields": [
        {"id": 1, "name": "Mandant", "data_type": "string"},
        {"id": 2, "name": "Betrag", "data_type": "monetary"},
        {"id": 3, "name": "Bezahlt", "data_type": "boolean"},
        {"id": 4, "name": "Termin", "data_type": "date"},
        {
            "id": 5,
            "name": "Kategorie",
            "data_type": "select",
            "extra_data": {
                "select_options": [
                    {"id": "a", "label": "Allgemein"},
                    {"id": "b", "label": "Vertraulich"},
                ]
            },
        },
        {"id": 6, "name": "Verweise", "data_type": "documentlink"},
        {"id": 7, "name": "Anzahl", "data_type": "integer"},
        {"id": 8, "name": "Faktor", "data_type": "float"},
        {"id": 9, "name": "Website", "data_type": "url"},
        {"id": 10, "name": "Beschreibung", "data_type": "longtext"},
    ],
}
DOCS = [
    {
        "id": 101,
        "title": "Rechnung Firma A",
        "document_type": 1,
        "created": "2026-10-01",
        "storage_path": 1,
        "correspondent": 1,
        "content": "PRIVATE OCR NOT FOR API",
        "custom_fields": [
            {"field": 1, "value": "A"},
            {"field": 2, "value": "120.00"},
            {"field": 3, "value": True},
            {"field": 5, "value": "a"},
        ],
    },
    {
        "id": 202,
        "title": "Geheimer Vertrag",
        "document_type": 2,
        "created": "2026-10-02",
        "storage_path": 2,
        "correspondent": 2,
        "custom_fields": [{"field": 1, "value": "B"}, {"field": 5, "value": "b"}],
    },
    {
        "id": 303,
        "title": "Anderer Mandant",
        "storage_path": 1,
        "correspondent": 1,
        "custom_fields": [{"field": 1, "value": "B"}],
    },
]


def matches(expression, document):
    if expression[0] == "AND":
        return all(matches(e, document) for e in expression[1])
    if expression[0] == "OR":
        return any(matches(e, document) for e in expression[1])
    identity, op, expected = expression
    fields = {v["field"]: v["value"] for v in document["custom_fields"]}
    value = fields.get(identity)
    if op == "exists":
        return (identity in fields) == expected
    if op == "isnull":
        return identity in fields and (value is None) == expected
    if op == "exact":
        return identity in fields and value == expected
    if op == "in":
        return value in expected
    if op == "icontains":
        return value is not None and str(expected).lower() in str(value).lower()
    if op == "contains":
        return value is not None and all(v in value for v in expected)
    if op == "range":
        return value is not None and expected[0] <= value <= expected[1]
    raise AssertionError(op)


def example_pdf():
    content = b"BT /F1 22 Tf 70 740 Td (Rechnung Firma A) Tj 0 -40 Td /F1 12 Tf (Betrag: 120,00 EUR) Tj ET"
    objects = [
        b"<</Type /Catalog /Pages 2 0 R>>",
        b"<</Type /Pages /Kids [3 0 R] /Count 1>>",
        b"<</Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources <</Font <</F1 4 0 R>>>> /Contents 5 0 R>>",
        b"<</Type /Font /Subtype /Type1 /BaseFont /Helvetica>>",
        b"<</Length " + str(len(content)).encode() + b">>\nstream\n" + content + b"\nendstream",
    ]
    output = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(output)
    output += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode()
    output += f"trailer\n<</Size 6 /Root 1 0 R>>\nstartxref\n{xref}\n%%EOF".encode()
    return output


def example_thumbnail():
    """Small deterministic PNG document, shared by API and browser fixtures."""

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    rows = bytearray()
    for y in range(128):
        rows.append(0)
        for x in range(96):
            color = (255, 255, 255)
            if 10 <= x < 66 and 14 <= y < 23:
                color = (33, 76, 60)
            elif 10 <= x < 84 and y in (36, 37, 46, 47, 56, 57, 66, 67, 94, 95):
                color = (165, 175, 165)
            rows.extend(color)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 96, 128, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )


class FakePaperless:
    def __init__(self):
        self.calls = []
        self.catalog = copy.deepcopy(CATALOG)
        self.docs = copy.deepcopy(DOCS)
        self.users = [
            {
                "id": 11,
                "username": "anna",
                "email": "anna@example.com",
                "is_active": True,
                "is_superuser": False,
                "groups": [7],
                "user_permissions": [],
                "inherited_permissions": ["documents.view_document"],
            }
        ]
        self.permissions = {
            101: {"owner": 99, "users": [], "groups": [7]},
            202: {"owner": 99, "users": [], "groups": [8]},
            303: {"owner": 99, "users": [], "groups": []},
        }
        self.remote_error = None
        self.remote_header = "Remote-User"
        self.error = None
        self.thumbnail_status = 200
        self.thumbnail_content_type = "image/png"

    def handle(self, request):
        self.calls.append(request)
        assert request.method == "GET", "Paperless must remain read-only"
        username = request.headers.get(self.remote_header)
        user = None
        if username is not None:
            assert "authorization" not in request.headers
            assert request.url.path.startswith("/api/documents/")
            if self.remote_error:
                return httpx.Response(self.remote_error)
            user = next((u for u in self.users if u["username"] == username), None)
            if not user or not user["is_active"]:
                return httpx.Response(401)
            if not (
                user["is_superuser"]
                or "view_document" in user["user_permissions"]
                or "documents.view_document" in user["inherited_permissions"]
            ):
                return httpx.Response(403)
        else:
            assert request.headers["authorization"] == "Token test-token"

        def visible(doc_id):
            if user is None or user["is_superuser"]:
                return True
            perms = self.permissions.get(doc_id, {"owner": 99, "users": [], "groups": []})
            return (
                perms["owner"] is None
                or perms["owner"] == user["id"]
                or user["id"] in perms["users"]
                or bool(set(user["groups"]) & set(perms["groups"]))
            )

        if self.error:
            return httpx.Response(self.error)
        resource = request.url.path.removeprefix("/api/").strip("/")
        if resource == "users":
            page = int(request.url.params.get("page", 1))
            size = int(request.url.params.get("page_size", 100))
            return httpx.Response(
                200,
                json={
                    "count": len(self.users),
                    "next": "http://untrusted.test/" if page * size < len(self.users) else None,
                    "results": self.users[(page - 1) * size : page * size],
                },
            )
        if resource.startswith("users/"):
            found = next((u for u in self.users if u["id"] == int(resource.split("/")[1])), None)
            return httpx.Response(200, json=found) if found else httpx.Response(404)
        if resource.startswith("documents/") and not visible(int(resource.split("/")[1])):
            return httpx.Response(403)
        if resource in self.catalog:
            return httpx.Response(
                200,
                json={
                    "count": len(self.catalog[resource]),
                    "next": None,
                    "results": self.catalog[resource],
                },
            )
        if resource == "documents":
            docs = [d for d in self.docs if visible(d["id"])]
            for param, field in [
                ("id__in", "id"),
                ("storage_path__id__in", "storage_path"),
                ("correspondent__id__in", "correspondent"),
                ("document_type__id__in", "document_type"),
            ]:
                if param in request.url.params:
                    ids = [int(i) for i in request.url.params[param].split(",")]
                    docs = [d for d in docs if d.get(field) in ids]
            if "custom_field_query" in request.url.params:
                expression = json.loads(request.url.params["custom_field_query"])
                docs = [d for d in docs if matches(expression, d)]
            docs.sort(key=lambda d: d["id"], reverse=True)
            size = int(request.url.params.get("page_size", 25))
            start = (int(request.url.params.get("page", 1)) - 1) * size
            results = docs[start : start + size]
            if request.url.params.get("fields") == "id":
                results = [{"id": doc["id"]} for doc in results]
            return httpx.Response(200, json={"count": len(docs), "next": None, "results": results})
        if resource.endswith("/thumb"):
            return httpx.Response(
                self.thumbnail_status,
                stream=httpx.ByteStream(example_thumbnail()),
                headers={"Content-Type": self.thumbnail_content_type},
            )
        if resource.endswith(("/preview", "/download")):
            content = example_pdf()
            headers = {"Content-Type": "application/pdf", "Accept-Ranges": "bytes"}
            if request.headers.get("range") == "bytes=0-0":
                headers.update(
                    {"Content-Range": f"bytes 0-0/{len(content)}", "Content-Length": "1"}
                )
                return httpx.Response(206, stream=httpx.ByteStream(content[:1]), headers=headers)
            return httpx.Response(200, stream=httpx.ByteStream(content), headers=headers)
        return httpx.Response(404)


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        app_url="http://testserver",
        paperless_url="http://paperless.test",
        paperless_public_url="https://docs.example",
        paperless_token="test-token",
        secret_key="test-secret-" * 4,
        oidc_issuer="https://idp.test",
        oidc_client_id="searchbar",
        oidc_client_secret="oidc-test",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    fake = FakePaperless()
    app.state.paperless.remote_transport = httpx.MockTransport(fake.handle)
    app.state.paperless.http = httpx.AsyncClient(
        base_url="http://paperless.test/api/",
        headers={"Authorization": "Token test-token"},
        transport=httpx.MockTransport(fake.handle),
    )
    with app.state.db() as db:
        db.add(SearchConfiguration(id=1, custom_field_ids=[1, 5]))
        profile = Profile(
            name="Firma A",
            rules=Rules(
                storage_paths=[1], custom_fields=[{"field": 1, "op": "exact", "value": "A"}]
            ).model_dump(),
        )
        db.add(profile)
        db.flush()
        db.add(
            User(
                name="Admin",
                username="admin",
                local_code_digest=digest(settings, "admin-code"),
                is_admin=True,
                active=True,
            )
        )
        db.add(
            GuestCode(
                name="Gast A",
                digest=digest(settings, "guest-code"),
                profile_id=profile.id,
                expires_at=now() + 3600,
            )
        )
        db.commit()
    with TestClient(app) as client:
        yield app, client, fake


def login(client, admin=False):
    data = client.get("/api/auth/session").json()
    response = client.post(
        "/api/auth/code",
        json={"code": "admin-code" if admin else "guest-code"},
        headers={"X-CSRF-Token": data["csrf"]},
    )
    assert response.status_code == 200, response.text
    data = client.get("/api/auth/session").json()
    client.headers["X-CSRF-Token"] = data["csrf"]
    return data
