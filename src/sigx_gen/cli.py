"""Command-line interface for generating and checking stubs."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import importlib
from pathlib import Path
import sys

from sigx_gen.config import GenerationConfig
from sigx_gen.diagnostics import Diagnostic
from sigx_gen.discovery import discover_functions
from sigx_gen.engine import apply_transforms
from sigx_gen.writer import check_module_outputs, render_module_outputs, write_module_outputs


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for ``sigx-gen``.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(prog="sigx-gen", description="Generate .pyi stubs for decorated functions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate .pyi files")
    generate_parser.add_argument("--src-root", required=True, help="Source root to scan")
    generate_parser.add_argument("--out-root", required=False, help="Output root (defaults to --src-root)")
    generate_parser.add_argument("--check", action="store_true", help="Check mode without writing files")

    check_parser = subparsers.add_parser("check", help="Check generated output")
    check_parser.add_argument("--src-root", required=True, help="Source root to scan")
    check_parser.add_argument("--out-root", required=False, help="Output root (defaults to --src-root)")

    return parser


def run_generate(config: GenerationConfig) -> int:
    """Execute one generation or check run.

    Args:
        config: Runtime generation configuration.

    Returns:
        Exit code: ``0`` success, ``1`` check mismatch, ``2`` unrecoverable error.
    """
    if not config.src_root.exists() or not config.src_root.is_dir():
        _write_stderr(f"error: unreadable source root: {config.src_root}")
        return 2

    src_root_entry = str(config.src_root)
    inserted_path = False
    if src_root_entry not in sys.path:
        sys.path.insert(0, src_root_entry)
        inserted_path = True
    importlib.invalidate_caches()

    try:
        discovered = discover_functions(config.src_root)
        engine_result = apply_transforms(discovered)
        rendered = render_module_outputs(
            engine_result.functions,
            src_root=config.src_root,
            out_root=config.out_root,
        )
    except Exception as exc:  # noqa: BLE001
        _write_stderr(f"error: generation failed: {exc}")
        return 2
    finally:
        if inserted_path and src_root_entry in sys.path:
            sys.path.remove(src_root_entry)

    _emit_diagnostics(engine_result.diagnostics)

    if config.check:
        mismatches = check_module_outputs(rendered)
        for path in mismatches:
            _write_stderr(f"drift: {path}")
        return 1 if mismatches else 0

    write_module_outputs(rendered)
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

    src_root = Path(args.src_root)
    out_root = Path(args.out_root) if args.out_root else src_root
    check = args.command == "check" or args.check

    config = GenerationConfig(src_root=src_root, out_root=out_root, check=check)
    return run_generate(config)


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
