"""Backward-compatible wrappers for standalone writer helpers."""

from collections import defaultdict
from pathlib import Path

from sigx_gen.emit.standalone import check_outputs, write_outputs
from sigx_gen.pipeline.transformer import TransformedFunction
from sigx_gen.render import needs_any_import, render_signature


def render_module_outputs(
    functions: tuple[TransformedFunction, ...],
    *,
    src_root: Path,
    out_root: Path,
) -> dict[Path, str]:
    """Render outputs using compatibility function signature.

    Args:
        functions: Transformed functions for rendering.
        src_root: Source root path.
        out_root: Output root path.

    Returns:
        Mapping of output path to rendered content.
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
    """Write rendered outputs to disk.

    Args:
        rendered_outputs: Mapping from path to content.

    Returns:
        Written paths.
    """
    return write_outputs(rendered_outputs)


def check_module_outputs(rendered_outputs: dict[Path, str]) -> tuple[Path, ...]:
    """Check rendered outputs against disk.

    Args:
        rendered_outputs: Mapping from path to content.

    Returns:
        Mismatched paths.
    """
    return check_outputs(rendered_outputs)


__all__ = ["check_module_outputs", "render_module_outputs", "write_module_outputs"]


def _output_path(source_file: Path, *, src_root: Path, out_root: Path) -> Path:
    relative = source_file.relative_to(src_root)
    return out_root / relative.with_suffix(".pyi")


def _render_module_text(functions: list[TransformedFunction]) -> str:
    top_level_blocks: list[str] = []
    class_blocks: dict[str, list[str]] = defaultdict(list)
    rendered_signatures: list[str] = []
    needs_overload = False

    for function in functions:
        rendered = [render_signature(signature) for signature in function.signatures]
        rendered_signatures.extend(rendered)
        block, uses_overload = _render_function_block(function.function_name, rendered)
        needs_overload = needs_overload or uses_overload
        if function.class_name is None:
            top_level_blocks.append(block)
        else:
            class_blocks[function.class_name].append(_indent_block(block, spaces=4))

    blocks: list[str] = []
    typing_imports: list[str] = []
    if needs_any_import(rendered_signatures):
        typing_imports.append("Any")
    if needs_overload:
        typing_imports.append("overload")
    if typing_imports:
        blocks.append(f"from typing import {', '.join(sorted(typing_imports))}")

    if top_level_blocks:
        blocks.append("\n\n".join(top_level_blocks))

    for class_name in sorted(class_blocks):
        methods = "\n\n".join(class_blocks[class_name])
        blocks.append(f"class {class_name}:\n{methods}")

    if not blocks:
        return ""

    return "\n\n".join(blocks) + "\n"


def _render_function_block(function_name: str, rendered_signatures: list[str]) -> tuple[str, bool]:
    if len(rendered_signatures) == 1:
        return f"def {function_name}{rendered_signatures[0]}: ...", False

    lines: list[str] = []
    for signature in rendered_signatures:
        lines.append("@overload")
        lines.append(f"def {function_name}{signature}: ...")
    return "\n".join(lines), True


def _indent_block(block: str, *, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" for line in block.splitlines())
