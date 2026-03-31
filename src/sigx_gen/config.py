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
        fail_on_errors: Whether error diagnostics should fail the run.
        include: Optional include glob filters relative to ``src_root``.
        exclude: Optional exclude glob filters relative to ``src_root``.
    """

    src_root: Path
    out_root: Path
    check: bool = False
    fail_on_errors: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PatchConfig:
    """Configuration for planning and patching existing stubs.

    Attributes:
        src_root: Source root to scan.
        stub_root: Root containing existing stubs.
        check: Whether to compare output without writing files.
        fail_on_errors: Whether error diagnostics should fail the run.
        include: Optional include glob filters relative to ``src_root``.
        exclude: Optional exclude glob filters relative to ``src_root``.
    """

    src_root: Path
    stub_root: Path
    check: bool = False
    fail_on_errors: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanConfig:
    """Configuration for building a serialized transform plan.

    Attributes:
        src_root: Source root to scan.
        stub_root: Target stub root used for plan paths.
        plan_file: Output JSON plan file path.
        fail_on_errors: Whether error diagnostics should fail the run.
        include: Optional include glob filters relative to ``src_root``.
        exclude: Optional exclude glob filters relative to ``src_root``.
    """

    src_root: Path
    stub_root: Path
    plan_file: Path
    fail_on_errors: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ApplyConfig:
    """Configuration for applying a serialized transform plan.

    Attributes:
        plan_file: Input JSON plan file path.
        check: Whether to check without writing files.
        fail_on_errors: Whether error diagnostics should fail the run.
    """

    plan_file: Path
    check: bool = False
    fail_on_errors: bool = False
