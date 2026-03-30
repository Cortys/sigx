"""Standalone backend for deterministic full-module stub generation."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sigx_gen.emit.imports import collect_imported_names, collect_missing_module_imports
from sigx_gen.emit.render import needs_any_import, render_signature
from sigx_gen.model.signature import SignatureIR
from sigx_gen.model.symbols import DiscoveredFunction, DiscoveredModule
from sigx_gen.pipeline.discovery import extract_signature_from_node
from sigx_gen.pipeline.transformer import TransformedFunction


def render_standalone_outputs(
    modules: tuple[DiscoveredModule, ...],
    transformed_functions: tuple[TransformedFunction, ...],
    *,
    src_root: Path,
    out_root: Path,
) -> dict[Path, str]:
    """Render standalone stubs for modules containing transformed symbols.

    Args:
        modules: Discovered modules with complete symbol surfaces.
        transformed_functions: Functions with transformed signature sets.
        src_root: Source tree root.
        out_root: Output tree root.

    Returns:
        Mapping of target stub path to rendered content.
    """
    transformed_by_module: dict[str, dict[str, tuple[SignatureIR, ...]]] = defaultdict(dict)
    for function in transformed_functions:
        transformed_by_module[function.module_name][function.qualname] = function.signatures

    rendered: dict[Path, str] = {}
    for module in modules:
        module_transforms = transformed_by_module.get(module.module_name)
        if not module_transforms:
            continue

        output_path = _output_path(module.file_path, src_root=src_root, out_root=out_root)
        rendered[output_path] = _render_module_text(module, module_transforms)
    return rendered


def write_outputs(rendered_outputs: dict[Path, str]) -> tuple[Path, ...]:
    """Write rendered outputs to disk.

    Args:
        rendered_outputs: Mapping from output path to rendered content.

    Returns:
        Paths written to disk.
    """
    written: list[Path] = []
    for path in sorted(rendered_outputs):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered_outputs[path], encoding="utf-8")
        written.append(path)
    return tuple(written)


def check_outputs(rendered_outputs: dict[Path, str]) -> tuple[Path, ...]:
    """Compare rendered outputs to on-disk files.

    Args:
        rendered_outputs: Mapping from output path to rendered content.

    Returns:
        Paths with missing or mismatched content.
    """
    mismatches: list[Path] = []
    for path in sorted(rendered_outputs):
        expected = rendered_outputs[path]
        if not path.exists():
            mismatches.append(path)
            continue
        if path.read_text(encoding="utf-8") != expected:
            mismatches.append(path)
    return tuple(mismatches)


def _output_path(source_file: Path, *, src_root: Path, out_root: Path) -> Path:
    relative = source_file.relative_to(src_root)
    return out_root / relative.with_suffix(".pyi")


def _render_module_text(module: DiscoveredModule, transformed: dict[str, tuple[SignatureIR, ...]]) -> str:
    signature_map = {
        function.qualname: transformed.get(function.qualname, (extract_signature_from_node(function.node),))
        for function in module.functions
    }

    top_level_functions = [function for function in module.functions if function.class_name is None]
    methods_by_class: dict[str, list[DiscoveredFunction]] = defaultdict(list)
    for function in module.functions:
        if function.class_name is not None:
            methods_by_class[function.class_name].append(function)

    rendered_signature_strings = [
        render_signature(signature) for signatures in signature_map.values() for signature in signatures
    ]

    top_level_blocks: list[str] = []
    class_blocks: list[str] = []
    for function in top_level_functions:
        signatures = [render_signature(signature) for signature in signature_map[function.qualname]]
        top_level_blocks.append(_render_function_block(function.function_name, signatures))

    for class_name in module.class_names:
        methods = sorted(methods_by_class.get(class_name, []), key=lambda item: item.lineno)
        if not methods:
            class_blocks.append(f"class {class_name}: ...")
            continue

        rendered_methods = []
        for method in methods:
            signatures = [render_signature(signature) for signature in signature_map[method.qualname]]
            rendered_methods.append(_indent_block(_render_function_block(method.function_name, signatures), spaces=4))
        class_blocks.append(f"class {class_name}:\n{'\n\n'.join(rendered_methods)}")

    variable_lines = []
    for variable in module.variables:
        annotation = variable.annotation or "Any"
        variable_lines.append(f"{variable.name}: {annotation}")

    blocks: list[str] = []
    blocks.extend(_render_import_block(module, rendered_signature_strings, variable_lines, signature_map))
    if variable_lines:
        blocks.append("\n".join(variable_lines))
    if top_level_blocks:
        blocks.append("\n\n".join(top_level_blocks))
    if class_blocks:
        blocks.append("\n\n".join(class_blocks))
    return "\n\n".join(blocks) + "\n"


def _render_import_block(
    module: DiscoveredModule,
    rendered_signatures: list[str],
    variable_lines: list[str],
    signature_map: dict[str, tuple[SignatureIR, ...]],
) -> list[str]:
    import_lines = list(dict.fromkeys(module.import_statements))
    imported_names = collect_imported_names(module.import_statements)
    local_names = {variable.name for variable in module.variables}
    local_names.update(module.class_names)
    local_names.update(function.function_name for function in module.functions if function.class_name is None)
    all_signatures = tuple(signature for signatures in signature_map.values() for signature in signatures)
    for root_module in collect_missing_module_imports(
        all_signatures,
        imported_names=imported_names,
        local_symbol_names=local_names,
    ):
        import_line = f"import {root_module}"
        if import_line not in import_lines:
            import_lines.append(import_line)

    typing_imports: list[str] = []
    if needs_any_import(rendered_signatures) or any(": Any" in line for line in variable_lines):
        typing_imports.append("Any")
    if any(_is_overload_candidate(signatures) for signatures in signature_map.values()):
        typing_imports.append("overload")
    if typing_imports:
        typing_line = f"from typing import {', '.join(sorted(typing_imports))}"
        if typing_line not in import_lines:
            import_lines.append(typing_line)

    return import_lines


def _render_function_block(function_name: str, rendered_signatures: list[str]) -> str:
    if len(rendered_signatures) == 1:
        return f"def {function_name}{rendered_signatures[0]}: ..."

    lines: list[str] = []
    for signature in rendered_signatures:
        lines.append("@overload")
        lines.append(f"def {function_name}{signature}: ...")
    return "\n".join(lines)


def _indent_block(block: str, *, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" for line in block.splitlines())


def _is_overload_candidate(signatures: tuple[SignatureIR, ...]) -> bool:
    return len(signatures) > 1
