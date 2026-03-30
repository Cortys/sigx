"""Structured diagnostic primitives for generation runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DiagnosticLevel(StrEnum):
    """Severity levels for generator diagnostics."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Structured issue emitted while generating stubs.

    Attributes:
        level: Diagnostic severity level.
        code: Stable diagnostic code.
        message: Human-readable message.
        module_name: Source module name if known.
        qualname: Source function qualname if known.
        file_path: Source file path if known.
    """

    level: DiagnosticLevel
    code: str
    message: str
    module_name: str | None = None
    qualname: str | None = None
    file_path: str | None = None
