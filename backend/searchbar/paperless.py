import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from fastapi import HTTPException

from .schemas import CustomFilter, Rules, Search


class Paperless:
    def __init__(self, settings):
        self.settings = settings
        self.http = httpx.AsyncClient(
            base_url=settings.paperless_url + "/api/",
            headers={"Authorization": "Token " + settings.paperless_token.get_secret_value()},
            timeout=httpx.Timeout(30, connect=5),
            follow_redirects=False,
        )

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

    @staticmethod
    def check(r):
        if r.status_code == 404:
            raise HTTPException(404, "Dokument oder Ressource nicht gefunden.")
        if r.status_code in (401, 403):
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

    async def catalogs(self):
        import asyncio

        paths, people, fields = await asyncio.gather(
            self.catalog("storage_paths"),
            self.catalog("correspondents"),
            self.catalog("custom_fields"),
        )
        return {"storage_paths": paths, "correspondents": people, "custom_fields": fields}

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
        return {
            "count": data["count"],
            "results": [self.present(d, catalogs) for d in data["results"]],
        }

    def present(self, d: dict, catalogs: dict):
        def label(kind, identity):
            return next((v["name"] for v in catalogs[kind] if v["id"] == identity), None)

        fields = {f["id"]: f for f in catalogs["custom_fields"]}
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
