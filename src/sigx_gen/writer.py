"""Stub output grouping, checking, and file writing helpers."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sigx_gen.engine import TransformedFunction
from sigx_gen.render import needs_any_import, render_signature


def render_module_outputs(
    functions: tuple[TransformedFunction, ...],
    *,
    src_root: Path,
    out_root: Path,
) -> dict[Path, str]:
    """Render transformed signatures into per-module stub texts.

    Args:
        functions: Transformed function results.
        src_root: Source root used for relative output paths.
        out_root: Output root where stubs are mirrored.

    Returns:
        Mapping of output ``.pyi`` path to rendered text.
    """
    by_module: dict[str, list[TransformedFunction]] = defaultdict(list)
    for function in functions:
        by_module[function.module_name].append(function)

    rendered: dict[Path, str] = {}
    for module_name in sorted(by_module):
        module_functions = sorted(by_module[module_name], key=lambda item: item.qualname)
        output_path = _output_path(module_functions[0].file_path, src_root=src_root, out_root=out_root)
        rendered[output_path] = _render_module_text(module_functions)
    return rendered


def write_module_outputs(rendered_outputs: dict[Path, str]) -> tuple[Path, ...]:
    """Write rendered stub outputs to disk.

    Args:
        rendered_outputs: Output mapping produced by ``render_module_outputs``.

    Returns:
        Tuple of written file paths.
    """
    written: list[Path] = []
    for path in sorted(rendered_outputs):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered_outputs[path], encoding="utf-8")
        written.append(path)
    return tuple(written)


def check_module_outputs(rendered_outputs: dict[Path, str]) -> tuple[Path, ...]:
    """Check whether rendered outputs match on-disk files.

    Args:
        rendered_outputs: Output mapping produced by ``render_module_outputs``.

    Returns:
        Paths that differ from generated content.
    """
    mismatches: list[Path] = []
    for path in sorted(rendered_outputs):
        expected = rendered_outputs[path]
        if not path.exists():
            mismatches.append(path)
            continue
        existing = path.read_text(encoding="utf-8")
        if existing != expected:
            mismatches.append(path)
    return tuple(mismatches)


def _output_path(source_file: Path, *, src_root: Path, out_root: Path) -> Path:
    relative = source_file.relative_to(src_root)
    return out_root / relative.with_suffix(".pyi")


def _render_module_text(functions: list[TransformedFunction]) -> str:
    top_level_lines: list[str] = []
    class_lines: dict[str, list[str]] = defaultdict(list)
    rendered_signatures: list[str] = []

    for function in functions:
        signature = render_signature(function.signature)
        rendered_signatures.append(signature)
        line = f"def {function.function_name}{signature}: ..."
        if function.class_name is None:
            top_level_lines.append(line)
        else:
            class_lines[function.class_name].append(f"    {line}")

    blocks: list[str] = []
    if needs_any_import(rendered_signatures):
        blocks.append("from typing import Any")

    if top_level_lines:
        blocks.append("\n".join(top_level_lines))

    for class_name in sorted(class_lines):
        methods = "\n".join(class_lines[class_name])
        blocks.append(f"class {class_name}:\n{methods}")

    if not blocks:
        return ""

    return "\n\n".join(blocks) + "\n"
