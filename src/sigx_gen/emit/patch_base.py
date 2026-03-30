"""Shared interfaces and utilities for patch-style emit backends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sigx_gen.model.diagnostics import Diagnostic, DiagnosticLevel
from sigx_gen.model.plan import ModulePlan, TransformPlan


class StubPatchBackend(Protocol):
    """Backend protocol for patching one module stub file."""

    def patch_module(self, existing_text: str, module_plan: ModulePlan) -> tuple[str, tuple[Diagnostic, ...]]:
        """Patch one module stub text.

        Args:
            existing_text: Current on-disk stub text.
            module_plan: Plan entries targeting this module.

        Returns:
            Tuple of patched text and diagnostics.
        """


@dataclass(frozen=True, slots=True)
class PatchRunResult:
    """Result summary for applying a patch plan.

    Attributes:
        written_paths: Paths updated on disk.
        mismatches: Paths that would change in check mode.
        diagnostics: Diagnostics emitted while patching.
    """

    written_paths: tuple[Path, ...]
    mismatches: tuple[Path, ...]
    diagnostics: tuple[Diagnostic, ...]


def apply_patch_plan(
    plan: TransformPlan,
    *,
    backend: StubPatchBackend,
    check: bool,
) -> PatchRunResult:
    """Apply a transform plan to existing stub files.

    Args:
        plan: Transform plan to apply.
        backend: Concrete patch backend implementation.
        check: Whether to check drift without writing files.

    Returns:
        Patch run result summary.
    """
    written: list[Path] = []
    mismatches: list[Path] = []
    diagnostics: list[Diagnostic] = []
    for module_plan in plan.modules:
        if not module_plan.stub_file.exists():
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="SX020",
                    message=f"Stub file missing for patch backend: {module_plan.stub_file}",
                    module_name=module_plan.module_name,
                    file_path=str(module_plan.stub_file),
                )
            )
            continue

        current_text = module_plan.stub_file.read_text(encoding="utf-8")
        patched_text, backend_diagnostics = backend.patch_module(current_text, module_plan)
        diagnostics.extend(backend_diagnostics)

        if patched_text == current_text:
            continue
        if check:
            mismatches.append(module_plan.stub_file)
            continue

        module_plan.stub_file.parent.mkdir(parents=True, exist_ok=True)
        module_plan.stub_file.write_text(patched_text, encoding="utf-8")
        written.append(module_plan.stub_file)

    return PatchRunResult(
        written_paths=tuple(written),
        mismatches=tuple(mismatches),
        diagnostics=tuple(diagnostics),
    )
