"""Command-line interface for generating, planning, and applying stubs."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import importlib
from pathlib import Path
import sys

from sigx_gen.config import ApplyConfig, GenerationConfig, PlanConfig
from sigx_gen.emit.patch_base import apply_patch_plan
from sigx_gen.emit.patch_libcst import build_libcst_backend
from sigx_gen.emit.standalone import check_outputs, render_standalone_outputs_with_diagnostics, write_outputs
from sigx_gen.io.plan_json import read_plan_json, write_plan_json
from sigx_gen.model.diagnostics import Diagnostic
from sigx_gen.model.symbols import DiscoveredModule
from sigx_gen.pipeline.discovery import discover_modules
from sigx_gen.pipeline.planner import build_transform_plan
from sigx_gen.pipeline.transformer import TransformedFunction, apply_transforms


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for ``sigx-gen``.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(prog="sigx-gen", description="Generate and patch .pyi stubs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate or patch stubs")
    generate_parser.add_argument("--src-root", required=True, help="Source root to scan")
    generate_parser.add_argument("--out-root", required=False, help="Output root (defaults to --src-root)")
    generate_parser.add_argument("--check", action="store_true", help="Check mode without writing files")
    generate_parser.add_argument(
        "--backend",
        required=False,
        default="standalone",
        choices=["standalone", "patch"],
        help="Output backend to use",
    )

    check_parser = subparsers.add_parser("check", help="Check generated output")
    check_parser.add_argument("--src-root", required=True, help="Source root to scan")
    check_parser.add_argument("--out-root", required=False, help="Output root (defaults to --src-root)")
    check_parser.add_argument(
        "--backend",
        required=False,
        default="standalone",
        choices=["standalone", "patch"],
        help="Output backend to use",
    )

    plan_parser = subparsers.add_parser("plan", help="Build transform plan JSON")
    plan_parser.add_argument("--src-root", required=True, help="Source root to scan")
    plan_parser.add_argument("--stub-root", required=False, help="Stub root (defaults to --src-root)")
    plan_parser.add_argument("--plan-out", required=True, help="Output transform plan file")

    apply_parser = subparsers.add_parser("apply", help="Apply transform plan to existing stubs")
    apply_parser.add_argument("--plan", required=True, help="Transform plan JSON file")
    apply_parser.add_argument("--check", action="store_true", help="Check mode without writing files")

    return parser


def run_generate(config: GenerationConfig) -> int:  # noqa: PLR0911
    """Execute one generation or check run.

    Args:
        config: Runtime generation configuration.

    Returns:
        Exit code: ``0`` success, ``1`` check mismatch, ``2`` unrecoverable error.
    """
    if not config.src_root.exists() or not config.src_root.is_dir():
        _write_stderr(f"error: unreadable source root: {config.src_root}")
        return 2

    modules, transformed_functions, diagnostics_or_error = _discover_and_transform(config.src_root)
    if isinstance(diagnostics_or_error, str):
        _write_stderr(f"error: generation failed: {diagnostics_or_error}")
        return 2

    diagnostics = list(diagnostics_or_error)
    if config.backend == "standalone":
        rendered, render_diagnostics = render_standalone_outputs_with_diagnostics(
            modules,
            transformed_functions,
            src_root=config.src_root,
            out_root=config.out_root,
        )
        diagnostics.extend(render_diagnostics)
        _emit_diagnostics(tuple(diagnostics))
        if config.check:
            mismatches = check_outputs(rendered)
            for path in mismatches:
                _write_stderr(f"drift: {path}")
            return 1 if mismatches else 0

        write_outputs(rendered)
        return 0

    plan = build_transform_plan(
        modules,
        transformed_functions,
        src_root=config.src_root,
        stub_root=config.out_root,
    )
    try:
        backend = build_libcst_backend()
    except RuntimeError as exc:
        _write_stderr(f"error: {exc}")
        return 2

    patch_result = apply_patch_plan(plan, backend=backend, check=config.check)
    diagnostics.extend(patch_result.diagnostics)
    _emit_diagnostics(tuple(diagnostics))
    if config.check:
        for path in patch_result.mismatches:
            _write_stderr(f"drift: {path}")
        return 1 if patch_result.mismatches else 0
    return 0


def run_plan(config: PlanConfig) -> int:
    """Build and write a serialized transform plan.

    Args:
        config: Plan generation configuration.

    Returns:
        Process exit code.
    """
    if not config.src_root.exists() or not config.src_root.is_dir():
        _write_stderr(f"error: unreadable source root: {config.src_root}")
        return 2

    modules, transformed_functions, diagnostics_or_error = _discover_and_transform(config.src_root)
    if isinstance(diagnostics_or_error, str):
        _write_stderr(f"error: plan failed: {diagnostics_or_error}")
        return 2

    plan = build_transform_plan(
        modules,
        transformed_functions,
        src_root=config.src_root,
        stub_root=config.stub_root,
    )
    write_plan_json(plan, config.plan_file)
    _emit_diagnostics(diagnostics_or_error)
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
    try:
        backend = build_libcst_backend()
    except RuntimeError as exc:
        _write_stderr(f"error: {exc}")
        return 2

    patch_result = apply_patch_plan(plan, backend=backend, check=config.check)
    _emit_diagnostics(patch_result.diagnostics)
    if config.check:
        for path in patch_result.mismatches:
            _write_stderr(f"drift: {path}")
        return 1 if patch_result.mismatches else 0
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``sigx-gen`` command-line interface.

    Args:
        argv: Optional CLI argument vector.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in {"generate", "check"}:
        src_root = Path(args.src_root)
        out_root = Path(args.out_root) if args.out_root else src_root
        config = GenerationConfig(
            src_root=src_root,
            out_root=out_root,
            check=(args.command == "check") or bool(getattr(args, "check", False)),
            backend=args.backend,
        )
        return run_generate(config)

    if args.command == "plan":
        src_root = Path(args.src_root)
        stub_root = Path(args.stub_root) if args.stub_root else src_root
        config = PlanConfig(
            src_root=src_root,
            stub_root=stub_root,
            plan_file=Path(args.plan_out),
        )
        return run_plan(config)

    if args.command == "apply":
        config = ApplyConfig(plan_file=Path(args.plan), check=args.check)
        return run_apply(config)

    _write_stderr(f"error: unknown command '{args.command}'")
    return 2


def _discover_and_transform(
    src_root: Path,
) -> tuple[tuple[DiscoveredModule, ...], tuple[TransformedFunction, ...], tuple[Diagnostic, ...] | str]:
    src_root_entry = str(src_root)
    inserted_path = False
    if src_root_entry not in sys.path:
        sys.path.insert(0, src_root_entry)
        inserted_path = True
    importlib.invalidate_caches()

    try:
        modules = discover_modules(src_root)
        functions = tuple(function for module in modules for function in module.functions)
        transformer_result = apply_transforms(functions)
    except Exception as exc:  # noqa: BLE001
        return (), (), str(exc)
    finally:
        if inserted_path and src_root_entry in sys.path:
            sys.path.remove(src_root_entry)

    return modules, transformer_result.functions, transformer_result.diagnostics


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


if __name__ == "__main__":
    raise SystemExit(main())
