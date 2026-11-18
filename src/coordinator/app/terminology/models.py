# src/coordinator/app/terminology/models.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# نگاشت اولویت متنی فارسی به عدد (عدد کمتر = اولویت بالاتر)
_PRIORITY_MAP = {
    "خیلی زیاد": 10, "بسیار زیاد": 10,
    "زیاد": 50, "متوسط": 100, "کم": 500, "خیلی کم": 1000,
}

# نگاشت وضعیت فارسی به وضعیت داخلی
_STATUS_MAP = {
    "فعال": "active", "active": "active", "تأییدشده": "active", "تاییدشده": "active",
    "غیرفعال": "inactive", "inactive": "inactive", "ردشده": "inactive",
}


class TerminologyEntry(BaseModel):
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

    # --- فیلدهای جدید مطابق terms.json ---
    english_equivalent: str = Field(default="", max_length=300)
    product: str = Field(default="", max_length=200)
    entry_type: str = Field(default="", max_length=100)
    usage_rules: str = Field(default="", max_length=2000)
    forbidden_terms: list[str] = Field(default_factory=list, max_length=50)
    correct_example: str = Field(default="", max_length=2000)
    incorrect_example: str = Field(default="", max_length=2000)
    language: str = Field(default="fa", max_length=20)
    notes: str = Field(default="", max_length=2000)

    @field_validator(
        "aliases", "app_ids", "related_terms", "search_terms", "intent_hints",
        "forbidden_terms",
        mode="before",
    )
    @classmethod
    def _strip_list_values(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("مقدار باید آرایه باشد.")
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, value):
        if isinstance(value, bool):
            raise ValueError("اولویت باید عدد یا یکی از سطوح متنی باشد.")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.isdigit():
                return int(text)
            if text in _PRIORITY_MAP:
                return _PRIORITY_MAP[text]
        raise ValueError(f"مقدار اولویت نامعتبر است: {value!r}")

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, value):
        if isinstance(value, str):
            text = value.strip()
            if text.lower() in {"active", "inactive"}:
                return text.lower()
            if text in _STATUS_MAP:
                return _STATUS_MAP[text]
        return value

    @model_validator(mode="after")
    def _sync_app_ids_from_product(self):
        # اگر app_ids خالی بود، از product پر شود
        if not self.app_ids and self.product:
            self.app_ids = [p.strip() for p in self.product.split("؛") if p.strip()]
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
    # جدید:
    english_equivalent: str = ""
    forbidden_terms: list[str] = Field(default_factory=list)
    usage_rules: str = ""
    product: str = ""
    entry_type: str = ""