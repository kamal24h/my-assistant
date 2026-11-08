"""Validated data models for the organization glossary."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TerminologyEntry(BaseModel):
    """A canonical business/software term and its linguistic variants.

    `app_ids=[]` means the entry is global. Otherwise it is only considered
    for the listed ERP applications.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    term_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    canonical: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    definition: str = Field(default="", max_length=1200)
    domain: str = Field(default="general", max_length=100)
    app_ids: list[str] = Field(default_factory=list, max_length=50)
    entity_type: str | None = Field(default=None, max_length=100)
    related_terms: list[str] = Field(default_factory=list, max_length=30)
    search_terms: list[str] = Field(default_factory=list, max_length=30)
    intent_hints: list[str] = Field(default_factory=list, max_length=20)
    form_id: str | None = Field(default=None, max_length=100)
    status: Literal["active", "inactive"] = "active"
    priority: int = Field(default=100, ge=1, le=1000)

    @field_validator(
        "aliases", "app_ids", "related_terms", "search_terms", "intent_hints",
        mode="before",
    )
    @classmethod
    def _strip_list_values(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("مقدار باید آرایه باشد.")
        return [str(item).strip() for item in value if str(item).strip()]


class TerminologyFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    terms: list[TerminologyEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_term_ids(self):
        ids = [entry.term_id for entry in self.terms]
        if len(ids) != len(set(ids)):
            raise ValueError("term_id باید در فایل واژه‌نامه یکتا باشد.")
        return self


class TerminologyMatch(BaseModel):
    term_id: str
    canonical: str
    matched_text: str
    definition: str = ""
    domain: str = "general"
    entity_type: str | None = None
    related_terms: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    intent_hints: list[str] = Field(default_factory=list)
    form_id: str | None = None
    priority: int = 100


class TerminologyResolution(BaseModel):
    original_text: str
    normalized_text: str
    matches: list[TerminologyMatch] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    context: str = ""

    @property
    def matched_term_ids(self) -> list[str]:
        return list(dict.fromkeys(match.term_id for match in self.matches))
