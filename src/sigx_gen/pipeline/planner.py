"""Plan construction for patching existing stubs from transform results."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sigx_gen.emit.imports import collect_imported_names, collect_missing_module_imports
from sigx_gen.emit.render import render_signature
from sigx_gen.model.plan import ModulePlan, SymbolPlan, TransformPlan
from sigx_gen.model.symbols import DiscoveredModule
from sigx_gen.pipeline.transformer import TransformedFunction


def build_transform_plan(
    modules: tuple[DiscoveredModule, ...],
    transformed_functions: tuple[TransformedFunction, ...],
    *,
    src_root: Path,
    stub_root: Path,
) -> TransformPlan:
    """Build a patch plan from transformed functions.

    Args:
        modules: Discovered modules.
        transformed_functions: Transformed symbols and signature sets.
        src_root: Source tree root.
        stub_root: Root path containing target stubs.

    Returns:
        Serializable transform plan.
    """
    module_index = {module.module_name: module for module in modules}
    by_module: dict[str, list[TransformedFunction]] = defaultdict(list)
    for function in transformed_functions:
        by_module[function.module_name].append(function)

    module_plans: list[ModulePlan] = []
    for module_name in sorted(by_module):
        module = module_index[module_name]
        transformed = sorted(by_module[module_name], key=lambda item: item.qualname)
        symbols = tuple(
            SymbolPlan(
                qualname=function.qualname,
                function_name=function.function_name,
                class_name=function.class_name,
                rendered_signatures=tuple(render_signature(signature) for signature in function.signatures),
            )
            for function in transformed
        )

        typing_imports: list[str] = []
        if any(any("Any" in signature for signature in symbol.rendered_signatures) for symbol in symbols):
            typing_imports.append("Any")
        if any(len(symbol.rendered_signatures) > 1 for symbol in symbols):
            typing_imports.append("overload")

        imported_names = collect_imported_names(module.import_statements)
        local_names = {variable.name for variable in module.variables}
        local_names.update(module.class_names)
        local_names.update(function.function_name for function in module.functions if function.class_name is None)
        all_signatures = tuple(signature for function in transformed for signature in function.signatures)
        module_imports = collect_missing_module_imports(
            all_signatures,
            imported_names=imported_names,
            local_symbol_names=local_names,
        )

        stub_file = stub_root / module.file_path.relative_to(src_root)
        module_plans.append(
            ModulePlan(
                module_name=module_name,
                source_file=module.file_path,
                stub_file=stub_file.with_suffix(".pyi"),
                typing_imports=tuple(sorted(set(typing_imports))),
                module_imports=module_imports,
                symbols=symbols,
            )
        )
    return TransformPlan(modules=tuple(module_plans))
