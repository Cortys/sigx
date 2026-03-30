"""Configuration model for generation and check runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    """Configuration for a stub generation run.

    Attributes:
        src_root: Source root to scan for Python files.
        out_root: Output root for generated ``.pyi`` files.
        check: Whether to compare output without writing files.
        backend: Output backend name.
    """

    src_root: Path
    out_root: Path
    check: bool = False
    backend: Literal["standalone", "patch"] = "standalone"


@dataclass(frozen=True, slots=True)
class PlanConfig:
    """Configuration for building a serialized transform plan.

    Attributes:
        src_root: Source root to scan.
        stub_root: Target stub root used for plan paths.
        plan_file: Output JSON plan file path.
    """

    src_root: Path
    stub_root: Path
    plan_file: Path


@dataclass(frozen=True, slots=True)
class ApplyConfig:
    """Configuration for applying a serialized transform plan.

    Attributes:
        plan_file: Input JSON plan file path.
        check: Whether to check without writing files.
    """

    plan_file: Path
    check: bool = False
