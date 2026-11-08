"""Organization terminology / glossary support for the ERP assistant."""

from app.terminology.resolver import (
    TerminologyResolver,
    get_terminology_resolver,
)
from app.terminology.models import (
    TerminologyEntry,
    TerminologyMatch,
    TerminologyResolution,
)

__all__ = [
    "TerminologyEntry",
    "TerminologyMatch",
    "TerminologyResolution",
    "TerminologyResolver",
    "get_terminology_resolver",
]
