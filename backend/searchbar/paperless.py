import asyncio
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .cache import AsyncCache
from .schemas import CustomFilter, Rules, Search


def normalize_email(value: str) -> str:
    return value.strip().casefold()


class PaperlessUser(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int = Field(gt=0)
    username: str = Field(min_length=1)
    email: str
    is_active: bool
    is_superuser: bool
    user_permissions: list[str]
    inherited_permissions: list[str]

    @property
    def can_view_documents(self):
        return self.is_active and (
            self.is_superuser
            or "view_document" in self.user_permissions
            or "documents.view_document" in self.inherited_permissions
        )


class Paperless:
    def __init__(self, settings, *, username=None, transport=None):
        self.catalog_cache = AsyncCache(settings.paperless_cache_ttl_seconds, capacity=1)
        self.filter_cache = AsyncCache(settings.paperless_cache_ttl_seconds)
        self.probe_slots = asyncio.Semaphore(6)
        self.settings = settings
        self.username = username
        self.remote_transport = transport
        self.http = httpx.AsyncClient(
            base_url=settings.paperless_url + "/api/",
            headers=(
                {settings.paperless_remote_user_header: username}
                if username is not None
                else {"Authorization": "Token " + settings.paperless_token.get_secret_value()}
            ),
            timeout=httpx.Timeout(30, connect=5),
            follow_redirects=False,
            transport=transport,
        )

    def for_user(self, username: str):
        # Each incoming request owns a client and cookie jar, including file streams.
        try:
            encoded = username.encode("ascii")
        except UnicodeEncodeError as exc:
            raise HTTPException(
                403, "Paperless-Benutzername muss für Remote-User ASCII enthalten."
            ) from exc
        if not encoded or any(c < 33 or c > 126 for c in encoded):
            raise HTTPException(403, "Paperless-Benutzername ist für Remote-User ungültig.")
        return Paperless(self.settings, username=username, transport=self.remote_transport)

    @staticmethod
    def parse_user(data):
        try:
            return PaperlessUser.model_validate(data)
        except ValidationError as exc:
            raise HTTPException(502, "Ungültige Paperless-Benutzerantwort.") from exc

    async def user_for_email(self, email: str):
        users = [self.parse_user(u) for u in await self.catalog("users")]
        matches = [u for u in users if normalize_email(u.email) == email]
        if len(matches) != 1:
            raise HTTPException(
                403,
                "Kein eindeutiges Paperless-Konto zur bestätigten E-Mail-Adresse gefunden. "
                "Paperless-Konto prüfen und erneut anmelden.",
            )
        if not matches[0].is_active:
            raise HTTPException(403, "Dein Paperless-Konto ist deaktiviert.")
        return matches[0]

    async def linked_user(self, principal):
        if not principal.paperless_user_id or not principal.verified_email:
            raise HTTPException(
                403,
                principal.paperless_link_error
                or "Keine Paperless-Zuordnung vorhanden. Bitte erneut anmelden.",
            )
        try:
            data = await self.get(f"users/{principal.paperless_user_id}/")
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(
                    403, "Das zugeordnete Paperless-Konto existiert nicht mehr."
                ) from exc
            raise
        user = self.parse_user(data)
        if (
            user.id != principal.paperless_user_id
            or normalize_email(user.email) != principal.verified_email
        ):
            raise HTTPException(
                403, "Die Paperless-Zuordnung hat sich geändert. Bitte erneut anmelden."
            )
        if not user.is_active:
            raise HTTPException(403, "Dein Paperless-Konto ist deaktiviert.")
        if not user.can_view_documents:
            raise HTTPException(403, "Dein Paperless-Konto hat keine Dokumentleserechte.")
        return user

    async def get(self, path: str, params=None):
        try:
            r = await self.http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise HTTPException(502, "Paperless ist nicht erreichbar.") from exc
        self.check(r)
        try:
            return r.json()
        except ValueError as exc:
            raise HTTPException(502, "Ungültige Antwort von Paperless.") from exc

    def check(self, r):
        if r.status_code == 404:
            raise HTTPException(404, "Dokument oder Ressource nicht gefunden.")
        if r.status_code in (401, 403):
            if self.username is not None:
                raise HTTPException(
                    403,
                    "Paperless hat den Dokumentzugriff verweigert. "
                    "Dokumentrechte und Remote-User-Konfiguration prüfen.",
                )
            raise HTTPException(
                502, "Der technische Paperless-Zugang hat keine ausreichenden Leserechte."
            )
        if r.status_code == 400:
            raise HTTPException(422, "Paperless hat den Filter abgelehnt. Felder und Werte prüfen.")
        if r.status_code not in (200, 206, 416):
            raise HTTPException(502, "Paperless hat eine unerwartete Antwort geliefert.")

    async def catalog(self, resource: str):
        results = []
        page = 1
        while True:
            data = await self.get(f"{resource}/", {"page": page, "page_size": 100})
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise HTTPException(502, "Ungültige Paperless-Auswahlliste.")
            results.extend(data["results"])
            if not data.get("next"):
                return results
            page += 1  # Never follow an upstream URL with our credential.
            if page > 1000:
                raise HTTPException(502, "Paperless-Auswahlliste ist zu groß.")

    async def close(self):
        await self.filter_cache.close()
        await self.catalog_cache.close()
        await self.http.aclose()

    async def catalogs(self):
        entry = await self.catalog_cache.get("catalogs", self._catalogs)
        return {**entry.value, "_generation": entry.generation, "_expires_at": entry.expires_at}

    async def _catalogs(self):
        tasks = [
            asyncio.create_task(self.catalog(resource))
            for resource in ("storage_paths", "correspondents", "custom_fields", "document_types")
        ]
        try:
            paths, people, fields, document_types = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        return {
            "storage_paths": paths,
            "correspondents": people,
            "custom_fields": fields,
            "document_types": document_types,
        }

    async def validate_rules(self, rules: Rules, catalogs: dict):
        for key in ("storage_paths", "correspondents"):
            available = {v["id"] for v in catalogs[key]}
            if not set(getattr(rules, key)) <= available:
                raise HTTPException(
                    409, "Freigabe enthält gelöschte oder nicht lesbare Referenzen."
                )
        if rules.document_ids:
            data = await self.get(
                "documents/",
                {
                    "id__in": ",".join(map(str, rules.document_ids)),
                    "page_size": 100,
                    "fields": "id",
                },
            )
            if {d["id"] for d in data["results"]} != set(rules.document_ids):
                raise HTTPException(409, "Freigabe enthält gelöschte oder nicht lesbare Dokumente.")
        for f in rules.custom_fields:
            try:
                custom_expression(f, catalogs["custom_fields"])
            except HTTPException as exc:
                raise HTTPException(
                    409, "Freigabe enthält ein ungültiges Custom Field oder einen ungültigen Wert."
                ) from exc

    async def search(self, search: Search, rules: Rules, catalogs: dict):
        params = compile_query(search, rules, catalogs["custom_fields"])
        if params is None:
            return {"count": 0, "results": []}
        data = await self.get("documents/", params)
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("results"), list)
            or not isinstance(data.get("count"), int)
        ):
            raise HTTPException(502, "Ungültige Dokumentenliste von Paperless.")
        indexes = {
            key: {item["id"]: item for item in catalogs[key]}
            for key in ("storage_paths", "correspondents", "custom_fields", "document_types")
        }
        return {
            "count": data["count"],
            "results": [self.present(d, indexes) for d in data["results"]],
        }

    async def exists(self, search: Search, rules: Rules, catalogs: dict):
        params = compile_query(search, rules, catalogs["custom_fields"])
        if params is None:
            return False
        params.update(page=1, page_size=1, fields="id")
        data = await self.get("documents/", params)
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("results"), list)
            or type(data.get("count")) is not int
        ):
            raise HTTPException(502, "Ungültige Dokumentenliste von Paperless.")
        return bool(data["results"])

    async def visible_choices(self, choices, query, rules, catalogs):
        """Bound task count as well as app-wide concurrent probe requests."""
        items = iter(enumerate(choices))
        visible = [False] * len(choices)

        async def worker():
            for index, choice in items:
                async with self.probe_slots:
                    visible[index] = await self.exists(query(choice), rules, catalogs)

        tasks = [asyncio.create_task(worker()) for _ in range(min(6, len(choices)))]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return [choice for choice, allowed in zip(choices, visible, strict=True) if allowed]

    def present(self, d: dict, indexes: dict):
        def label(kind, identity):
            item = indexes[kind].get(identity)
            return item["name"] if item else None

        fields = indexes["custom_fields"]
        custom = []
        for item in d.get("custom_fields", []):
            f = fields.get(item["field"])
            if not f:
                continue
            value = item.get("value")
            if f["data_type"] == "select":
                value = next(
                    (
                        o["label"]
                        for o in (f.get("extra_data") or {}).get("select_options", [])
                        if o["id"] == value
                    ),
                    value,
                )
            custom.append({"field": f["id"], "name": f["name"], "value": value})
        # Explicit allowlist: no content, owner information, internal paths or upstream URLs.
        return {
            "id": d["id"],
            "title": d.get("title", ""),
            "created": d.get("created"),
            "correspondent": label("correspondents", d.get("correspondent")),
            "storage_path": label("storage_paths", d.get("storage_path")),
            "document_type": label("document_types", d.get("document_type")),
            "custom_fields": custom,
            "paperless_url": f"{self.settings.paperless_public_url}/documents/{d['id']}/",
        }


def operators(data_type):
    basic = ["exact", "in", "exists", "empty"]
    if data_type in ("string", "longtext", "url"):
        return basic + ["icontains"]
    if data_type in ("integer", "float", "monetary", "date"):
        return basic + ["range"]
    if data_type == "documentlink":
        return ["exact", "contains", "exists", "empty"]
    if data_type in ("boolean", "select"):
        return basic
    return []


def custom_expression(f: CustomFilter, fields: list[dict]) -> list:
    field = next((v for v in fields if v["id"] == f.field), None)
    if not field or f.op not in operators(field["data_type"]):
        raise HTTPException(422, "Unbekanntes Custom Field oder ungültiger Operator.")
    kind = field["data_type"]
    value = f.value
    if f.op == "exists":
        if type(value) is not bool:
            raise HTTPException(422, "Vorhanden erwartet Ja oder Nein.")
        return [f.field, "exists", value]
    if f.op == "empty":
        parts = [[f.field, "isnull", True]]
        if kind in ("string", "longtext", "url"):
            parts.append([f.field, "exact", ""])
        if kind == "documentlink":
            parts.append([f.field, "exact", []])
        return ["OR", parts] if len(parts) > 1 else parts[0]

    def scalar(v: Any):
        valid = False
        if kind in ("string", "longtext", "url"):
            valid = isinstance(v, str) and len(v) <= 2000
        elif kind == "boolean":
            valid = type(v) is bool
        elif kind == "integer":
            valid = type(v) is int
        elif kind in ("float", "monetary"):
            try:
                valid = type(v) in (int, float, str) and Decimal(str(v)).is_finite()
            except InvalidOperation:
                valid = False
        elif kind == "date":
            try:
                valid = isinstance(v, str) and date.fromisoformat(v).isoformat() == v
            except ValueError:
                valid = False
        elif kind == "select":
            valid = v in [
                o["id"] for o in (field.get("extra_data") or {}).get("select_options", [])
            ]
        elif kind == "documentlink":
            valid = (
                isinstance(v, list) and len(v) <= 100 and all(type(i) is int and i > 0 for i in v)
            )
        if not valid:
            raise HTTPException(422, "Wert passt nicht zum Custom-Field-Typ.")
        return v

    if f.op in ("in", "range"):
        if (
            not isinstance(value, list)
            or not 1 <= len(value) <= 100
            or (f.op == "range" and len(value) != 2)
        ):
            raise HTTPException(422, "Eine gültige Werteliste bzw. Von/Bis-Werte angeben.")
        value = [scalar(v) for v in value]
        if f.op == "range":
            ordered = value if kind == "date" else [Decimal(str(v)) for v in value]
            if ordered[0] > ordered[1]:
                raise HTTPException(422, "Der Beginn muss vor dem Ende liegen.")
    else:
        value = scalar(value)
    return [f.field, f.op, value]


def compile_query(search: Search, rules: Rules, fields: list[dict]):
    if not rules.all_documents and not rules.restricted:
        return None
    params = {"page": search.page, "page_size": search.page_size, "ordering": "-id"}
    if search.document_type is not None:
        params["document_type__id__in"] = str(search.document_type)
    for attr, selected, upstream in (
        ("document_ids", search.document_id, "id__in"),
        ("storage_paths", search.storage_path, "storage_path__id__in"),
        ("correspondents", search.correspondent, "correspondent__id__in"),
    ):
        allowed = getattr(rules, attr)
        if selected is not None and allowed and selected not in allowed:
            return None
        ids = [selected] if selected is not None else allowed
        if ids:
            params[upstream] = ",".join(map(str, ids))
    terms = [custom_expression(f, fields) for f in [*rules.custom_fields, *search.custom_fields]]

    # Paperless limits queries to 20 atoms; never discard permission constraints.
    def atoms(expr):
        return sum(atoms(t) for t in expr[1]) if expr[0] in ("AND", "OR") else 1

    if sum(atoms(t) for t in terms) > 20:
        raise HTTPException(422, "Zu viele kombinierte Custom-Field-Bedingungen (maximal 20).")
    if terms:
        params["custom_field_query"] = json.dumps(["AND", terms], separators=(",", ":"))
    return params
