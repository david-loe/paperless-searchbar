import json

import pytest
from conftest import CATALOG
from fastapi import HTTPException
from pydantic import ValidationError
from searchbar.paperless import compile_query, custom_expression
from searchbar.schemas import CustomFilter, Rules, Search


@pytest.mark.parametrize(
    "field,op,value",
    [
        (1, "icontains", "a"),
        (2, "range", ["1.25", "99.99"]),
        (3, "exact", False),
        (4, "range", ["2026-01-01", "2026-12-31"]),
        (5, "in", ["a", "b"]),
        (6, "contains", [101]),
        (7, "exact", 42),
        (8, "range", [1.1, 2.2]),
        (9, "icontains", "example.org"),
        (10, "icontains", "Absatz"),
        (1, "exists", False),
    ],
)
def test_supported_types(field, op, value):
    expression = custom_expression(
        CustomFilter(field=field, op=op, value=value), CATALOG["custom_fields"]
    )
    assert expression == [field, op, value]


@pytest.mark.parametrize(
    "field,op,value",
    [
        (1, "range", ["a", "z"]),
        (2, "exact", "NaN"),
        (2, "exact", True),
        (3, "exact", "false"),
        (4, "exact", "2026-99-99"),
        (5, "exact", "missing"),
        (6, "contains", [-1]),
        (7, "exact", 1.5),
        (8, "range", [9, 1]),
        (1, "exists", "true"),
        (999, "exact", "x"),
        (2, "range", [1]),
    ],
)
def test_invalid_types(field, op, value):
    with pytest.raises(HTTPException):
        custom_expression(CustomFilter(field=field, op=op, value=value), CATALOG["custom_fields"])


def test_empty_string_and_null_are_combined():
    assert custom_expression(CustomFilter(field=1, op="empty"), CATALOG["custom_fields"]) == [
        "OR",
        [[1, "isnull", True], [1, "exact", ""]],
    ]


def test_scope_and_search_are_intersected_and_paginated_upstream():
    rules = Rules(
        storage_paths=[1, 2],
        correspondents=[1],
        custom_fields=[{"field": 1, "op": "in", "value": ["A", "B"]}],
    )
    search = Search(
        storage_path=1,
        custom_fields=[{"field": 3, "op": "exact", "value": True}],
        page=2,
        page_size=10,
    )
    params = compile_query(search, rules, CATALOG["custom_fields"])
    assert params["page"] == 2 and params["page_size"] == 10
    assert params["storage_path__id__in"] == "1"
    assert params["correspondent__id__in"] == "1"
    assert json.loads(params["custom_field_query"]) == [
        "AND",
        [[1, "in", ["A", "B"]], [3, "exact", True]],
    ]
    assert compile_query(Search(storage_path=3), rules, CATALOG["custom_fields"]) is None
    assert compile_query(Search(document_id=1), Rules(), []) is None


def test_ambiguous_all_documents_rejected():
    with pytest.raises(ValidationError):
        Rules(all_documents=True, storage_paths=[1])
