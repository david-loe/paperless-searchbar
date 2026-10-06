from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PositiveID = Annotated[int, Field(gt=0, strict=True)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomFilter(Input):
    field: PositiveID
    op: Literal["exact", "icontains", "range", "in", "contains", "exists", "empty"] = "exact"
    value: Any = None


class Rules(Input):
    all_documents: bool = False
    document_ids: list[PositiveID] = Field(default_factory=list, max_length=100)
    storage_paths: list[PositiveID] = Field(default_factory=list, max_length=100)
    correspondents: list[PositiveID] = Field(default_factory=list, max_length=100)
    custom_fields: list[CustomFilter] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def unambiguous(self):
        if self.all_documents and self.restricted:
            raise ValueError("Alle Dokumente darf nicht mit Einschränkungen kombiniert werden.")
        if len({c.field for c in self.custom_fields}) != len(self.custom_fields):
            raise ValueError(
                "Jedes Custom Field nur einmal pro Profil verwenden; mehrere Werte über 'in'."
            )
        return self

    @property
    def restricted(self) -> bool:
        return bool(
            self.document_ids or self.storage_paths or self.correspondents or self.custom_fields
        )


class Search(Input):
    document_id: PositiveID | None = None
    storage_path: PositiveID | None = None
    correspondent: PositiveID | None = None
    custom_fields: list[CustomFilter] = Field(default_factory=list, max_length=8)
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=25, ge=1, le=100)

    @property
    def has_filter(self):
        return bool(
            self.document_id or self.storage_path or self.correspondent or self.custom_fields
        )


class ProfileInput(Input):
    name: str = Field(min_length=1, max_length=120)
    rules: Rules


class CodeInput(Input):
    name: str = Field(min_length=1, max_length=120)
    profile_id: PositiveID
    expires_at: int


class UserUpdate(Input):
    profile_id: PositiveID | None = None
    active: bool
    is_admin: bool


class CodeLogin(Input):
    code: str = Field(min_length=1, max_length=128)


class DocumentField(BaseModel):
    field: int
    name: str
    value: Any


class DocumentResult(BaseModel):
    id: int
    title: str
    created: str | None
    correspondent: str | None
    storage_path: str | None
    custom_fields: list[DocumentField]
    paperless_url: str


class SearchResults(BaseModel):
    count: int
    results: list[DocumentResult]


class Choice(BaseModel):
    id: int
    name: str


class SelectOption(BaseModel):
    id: str
    label: str


class FieldDefinition(Choice):
    data_type: str
    operators: list[str]
    options: list[SelectOption]


class CatalogResponse(BaseModel):
    storage_paths: list[Choice]
    correspondents: list[Choice]
    custom_fields: list[FieldDefinition]
