"""Command-line interface for planning and patching stubs."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import fnmatch
import importlib
from pathlib import Path
import sys
import tempfile

from sigx_gen.bootstrap.basedpyright import generate_baseline_stubs
from sigx_gen.config import ApplyConfig, GenerationConfig, PatchConfig, PlanConfig
from sigx_gen.emit.patch_base import apply_patch_plan
from sigx_gen.emit.patch_libcst import build_libcst_backend
from sigx_gen.io.plan_json import read_plan_json, write_plan_json
from sigx_gen.model.diagnostics import Diagnostic, DiagnosticLevel
from sigx_gen.model.plan import TransformPlan
from sigx_gen.model.symbols import DiscoveredModule
from sigx_gen.pipeline.discovery import discover_modules
from sigx_gen.pipeline.planner import build_transform_plan
from sigx_gen.pipeline.transformer import TransformedFunction, apply_transforms


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for ``sigx-gen``.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="sigx-gen", description="Plan and patch .pyi stubs for transformed decorators."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate baseline stubs and patch transforms")
    _add_common_scope_args(generate_parser)
    generate_parser.add_argument(
        "--prune-unplanned",
        action="store_true",
        help="Remove .pyi files in out-root that are not part of the transform plan",
    )

    patch_parser = subparsers.add_parser("patch", help="Patch existing stubs with transform plan")
    patch_parser.add_argument("--src-root", required=True, help="Source root to scan")
    patch_parser.add_argument("--stub-root", required=False, help="Stub root (defaults to --src-root)")
    patch_parser.add_argument("--check", action="store_true", help="Check mode without writing files")
    patch_parser.add_argument("--fail-on-errors", action="store_true", help="Fail when any ERROR diagnostics occur")
    patch_parser.add_argument("--include", action="append", default=[], help="Include glob relative to src-root")
    patch_parser.add_argument("--exclude", action="append", default=[], help="Exclude glob relative to src-root")

    plan_parser = subparsers.add_parser("plan", help="Build transform plan JSON")
    plan_parser.add_argument("--src-root", required=True, help="Source root to scan")
    plan_parser.add_argument("--stub-root", required=False, help="Stub root (defaults to --src-root)")
    plan_parser.add_argument("--plan-out", required=True, help="Output transform plan file")
    plan_parser.add_argument("--fail-on-errors", action="store_true", help="Fail when any ERROR diagnostics occur")
    plan_parser.add_argument("--include", action="append", default=[], help="Include glob relative to src-root")
    plan_parser.add_argument("--exclude", action="append", default=[], help="Exclude glob relative to src-root")

    apply_parser = subparsers.add_parser("apply", help="Apply transform plan to existing stubs")
    apply_parser.add_argument("--plan", required=True, help="Transform plan JSON file")
    apply_parser.add_argument("--check", action="store_true", help="Check mode without writing files")
    apply_parser.add_argument("--fail-on-errors", action="store_true", help="Fail when any ERROR diagnostics occur")

    return parser


def run_generate(config: GenerationConfig) -> int:
    """Generate baseline stubs via basedpyright and patch transform overrides.

    Args:
        config: Generation configuration.

    Returns:
        Exit code: ``0`` success, ``1`` check mismatch, ``2`` unrecoverable error.
    """
    if not _is_readable_dir(config.src_root):
        _write_stderr(f"error: unreadable source root: {config.src_root}")
        return 2

    with tempfile.TemporaryDirectory(prefix="sigx-gen-staging-") as temp_dir:
        staging_root = Path(temp_dir) / "stubs"
        plan_or_error = _build_plan_from_source(
            src_root=config.src_root,
            stub_root=staging_root,
            include=config.include,
            exclude=config.exclude,
            action="generation",
        )
        if isinstance(plan_or_error, str):
            _write_stderr(f"error: generation failed: {plan_or_error}")
            return 2
        plan, diagnostics = plan_or_error

        try:
            generate_baseline_stubs(
                src_root=config.src_root,
                out_root=staging_root,
                module_targets=((module.module_name, module.stub_file) for module in plan.modules),
            )
        except RuntimeError as exc:
            _write_stderr(f"error: {exc}")
            return 2

        patch_exit_code = _apply_plan(
            plan=plan,
            check=False,
            fail_on_errors=config.fail_on_errors,
            initial_diagnostics=diagnostics,
        )
        if patch_exit_code == 2:
            return 2

        if config.prune_unplanned:
            _prune_unplanned_stubs(
                out_root=staging_root,
                planned_stub_paths=tuple(module.stub_file for module in plan.modules),
                check=False,
            )

        has_drift = _sync_generated_stubs(
            staging_root=staging_root,
            out_root=config.out_root,
            check=config.check,
            prune_unplanned=config.prune_unplanned,
        )
        if config.check and has_drift:
            return 1
        return 0


def run_patch(config: PatchConfig) -> int:
    """Patch existing stubs using discovered transform overrides.

    Args:
        config: Patch configuration.

    Returns:
        Exit code: ``0`` success, ``1`` check mismatch, ``2`` unrecoverable error.
    """
    if not _is_readable_dir(config.src_root):
        _write_stderr(f"error: unreadable source root: {config.src_root}")
        return 2

    plan_or_error = _build_plan_from_source(
        src_root=config.src_root,
        stub_root=config.stub_root,
        include=config.include,
        exclude=config.exclude,
        action="patch",
    )
    if isinstance(plan_or_error, str):
        _write_stderr(f"error: patch failed: {plan_or_error}")
        return 2
    plan, diagnostics = plan_or_error

    return _apply_plan(
        plan=plan,
        check=config.check,
        fail_on_errors=config.fail_on_errors,
        initial_diagnostics=diagnostics,
    )


def run_plan(config: PlanConfig) -> int:
    """Build and write a serialized transform plan.

    Args:
        config: Plan generation configuration.

    Returns:
        Process exit code.
    """
    if not _is_readable_dir(config.src_root):
        _write_stderr(f"error: unreadable source root: {config.src_root}")
        return 2

    plan_or_error = _build_plan_from_source(
        src_root=config.src_root,
        stub_root=config.stub_root,
        include=config.include,
        exclude=config.exclude,
        action="plan",
    )
    if isinstance(plan_or_error, str):
        _write_stderr(f"error: plan failed: {plan_or_error}")
        return 2
    plan, diagnostics = plan_or_error
    write_plan_json(plan, config.plan_file)
    _emit_diagnostics(diagnostics)
    if _should_fail_on_errors(config.fail_on_errors, diagnostics):
        return 2
    return 0


def run_apply(config: ApplyConfig) -> int:
    """Apply a serialized transform plan to existing stubs.

    Args:
        config: Plan apply configuration.

    Returns:
        Process exit code.
    """
    if not config.plan_file.exists() or not config.plan_file.is_file():
        _write_stderr(f"error: unreadable plan file: {config.plan_file}")
        return 2

    plan = read_plan_json(config.plan_file)
    return _apply_plan(
        plan=plan,
        check=config.check,
        fail_on_errors=config.fail_on_errors,
        initial_diagnostics=(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``sigx-gen`` command-line interface.

    Args:
        argv: Optional CLI argument vector.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        src_root = Path(args.src_root)
        out_root = Path(args.out_root) if args.out_root else src_root
        return run_generate(
            GenerationConfig(
                src_root=src_root,
                out_root=out_root,
                check=args.check,
                prune_unplanned=args.prune_unplanned,
                fail_on_errors=args.fail_on_errors,
                include=tuple(args.include),
                exclude=tuple(args.exclude),
            )
        )

    if args.command == "patch":
        src_root = Path(args.src_root)
        stub_root = Path(args.stub_root) if args.stub_root else src_root
        return run_patch(
            PatchConfig(
                src_root=src_root,
                stub_root=stub_root,
                check=args.check,
                fail_on_errors=args.fail_on_errors,
                include=tuple(args.include),
                exclude=tuple(args.exclude),
            )
        )

    if args.command == "plan":
        src_root = Path(args.src_root)
        stub_root = Path(args.stub_root) if args.stub_root else src_root
        return run_plan(
            PlanConfig(
                src_root=src_root,
                stub_root=stub_root,
                plan_file=Path(args.plan_out),
                fail_on_errors=args.fail_on_errors,
                include=tuple(args.include),
                exclude=tuple(args.exclude),
            )
        )

    if args.command == "apply":
        return run_apply(
            ApplyConfig(
                plan_file=Path(args.plan),
                check=args.check,
                fail_on_errors=args.fail_on_errors,
            )
        )

    _write_stderr(f"error: unknown command '{args.command}'")
    return 2


def _discover_and_transform(
    *,
    src_root: Path,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[
    tuple[DiscoveredModule, ...],
    tuple[TransformedFunction, ...],
    tuple[Diagnostic, ...] | str,
]:
    src_root_entry = str(src_root)
    inserted_path = False
    if src_root_entry not in sys.path:
        sys.path.insert(0, src_root_entry)
        inserted_path = True
    importlib.invalidate_caches()

    try:
        all_modules = discover_modules(src_root)
        modules = _filter_modules(all_modules, src_root=src_root, include=include, exclude=exclude)
        functions = tuple(function for module in modules for function in module.functions)
        module_files = {module.module_name: module.file_path for module in modules}
        transformer_result = apply_transforms(functions, module_files=module_files)
    except Exception as exc:  # noqa: BLE001
        return (), (), str(exc)
    finally:
        if inserted_path and src_root_entry in sys.path:
            sys.path.remove(src_root_entry)

    return modules, transformer_result.functions, transformer_result.diagnostics


def _build_plan_from_source(
    *,
    src_root: Path,
    stub_root: Path,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    action: str,
) -> tuple[TransformPlan, tuple[Diagnostic, ...]] | str:
    modules, transformed_functions, diagnostics_or_error = _discover_and_transform(
        src_root=src_root,
        include=include,
        exclude=exclude,
    )
    if isinstance(diagnostics_or_error, str):
        return diagnostics_or_error

    try:
        plan = build_transform_plan(
            modules,
            transformed_functions,
            src_root=src_root,
            stub_root=stub_root,
        )
    except Exception as exc:  # noqa: BLE001
        return f"{action} failed to build transform plan: {exc}"
    return plan, diagnostics_or_error


def _apply_plan(
    *,
    plan: TransformPlan,
    check: bool,
    fail_on_errors: bool,
    initial_diagnostics: tuple[Diagnostic, ...],
) -> int:
    try:
        backend = build_libcst_backend()
    except RuntimeError as exc:
        _write_stderr(f"error: {exc}")
        return 2

    patch_result = apply_patch_plan(plan, backend=backend, check=check)
    diagnostics = (*initial_diagnostics, *patch_result.diagnostics)
    _emit_diagnostics(diagnostics)

    if _should_fail_on_errors(fail_on_errors, diagnostics):
        return 2
    return _patch_result_exit_code(check=check, mismatches=patch_result.mismatches)


def _patch_result_exit_code(*, check: bool, mismatches: tuple[Path, ...]) -> int:
    if not check:
        return 0
    for path in mismatches:
        _write_stderr(f"drift: {path}")
    return 1 if mismatches else 0


def _is_readable_dir(path: Path) -> bool:
    return path.exists() and path.is_dir()


def _prune_unplanned_stubs(
    *,
    out_root: Path,
    planned_stub_paths: tuple[Path, ...],
    check: bool,
) -> tuple[Path, ...]:
    if not out_root.exists():
        return ()

    normalized_planned = {_normalize_path(path) for path in planned_stub_paths}
    unplanned_paths = tuple(
        sorted(path for path in out_root.rglob("*.pyi") if _normalize_path(path) not in normalized_planned)
    )
    if check:
        for path in unplanned_paths:
            _write_stderr(f"drift: {path}")
        return unplanned_paths

    for path in unplanned_paths:
        path.unlink()
    return ()


def _normalize_path(path: Path) -> Path:
    return path.resolve(strict=False)


def _sync_generated_stubs(
    *,
    staging_root: Path,
    out_root: Path,
    check: bool,
    prune_unplanned: bool,
) -> bool:
    staged_files = _collect_stub_files(staging_root)
    output_files = _collect_stub_files(out_root)
    has_drift = False

    for relative_path, staged_path in staged_files.items():
        output_path = out_root / relative_path
        existing_path = output_files.get(relative_path)
        staged_text = staged_path.read_text(encoding="utf-8")
        existing_text = None if existing_path is None else existing_path.read_text(encoding="utf-8")
        if existing_text == staged_text:
            continue

        has_drift = True
        if check:
            _write_stderr(f"drift: {output_path}")
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(staged_text, encoding="utf-8")

    if not prune_unplanned:
        return has_drift

    for relative_path, output_path in output_files.items():
        if relative_path in staged_files:
            continue
        has_drift = True
        if check:
            _write_stderr(f"drift: {output_path}")
            continue
        output_path.unlink()

    return has_drift


def _collect_stub_files(root: Path) -> dict[Path, Path]:
    if not root.exists():
        return {}
    return {path.relative_to(root): path for path in root.rglob("*.pyi")}


def _filter_modules(
    modules: tuple[DiscoveredModule, ...],
    *,
    src_root: Path,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[DiscoveredModule, ...]:
    if not include and not exclude:
        return modules

    filtered: list[DiscoveredModule] = []
    for module in modules:
        relative = module.file_path.relative_to(src_root).as_posix()
        if include and not any(fnmatch.fnmatch(relative, pattern) for pattern in include):
            continue
        if exclude and any(fnmatch.fnmatch(relative, pattern) for pattern in exclude):
            continue
        filtered.append(module)
    return tuple(filtered)


def _should_fail_on_errors(fail_on_errors: bool, diagnostics: tuple[Diagnostic, ...]) -> bool:
    if not fail_on_errors:
        return False
    return any(diagnostic.level == DiagnosticLevel.ERROR for diagnostic in diagnostics)


def _emit_diagnostics(diagnostics: tuple[Diagnostic, ...]) -> None:
    for diagnostic in diagnostics:
        location = diagnostic.module_name or "<unknown>"
        if diagnostic.qualname is not None:
            location = f"{location}:{diagnostic.qualname}"
        _write_stderr(f"{diagnostic.level} {diagnostic.code} {location} {diagnostic.message}")


def _write_stderr(message: str) -> None:
    """Write one diagnostic line to standard error.

    Args:
        message: Message to emit.
    """
    sys.stderr.write(f"{message}\n")


def _add_common_scope_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--src-root", required=True, help="Source root to scan")
    parser.add_argument("--out-root", required=False, help="Output root (defaults to --src-root)")
    parser.add_argument("--check", action="store_true", help="Check mode without writing files")
    parser.add_argument("--fail-on-errors", action="store_true", help="Fail when any ERROR diagnostics occur")
    parser.add_argument("--include", action="append", default=[], help="Include glob relative to src-root")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude glob relative to src-root")


if __name__ == "__main__":
    raise SystemExit(main())
