"""Configuration model for generation and check runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    """Configuration for a stub generation run.

    Attributes:
        src_root: Source root to scan for Python files.
        out_root: Output root for generated ``.pyi`` files.
        check: Whether to compare output without writing files.
    """

    src_root: Path
    out_root: Path
    check: bool = False
