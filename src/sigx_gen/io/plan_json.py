"""JSON serialization helpers for transform plans."""

from __future__ import annotations

import json
from pathlib import Path

from sigx_gen.model.plan import ModulePlan, SymbolPlan, TransformPlan


def write_plan_json(plan: TransformPlan, file_path: Path) -> None:
    """Write a transform plan to JSON.

    Args:
        plan: Plan to serialize.
        file_path: Output JSON path.
    """
    payload = {
        "modules": [
            {
                "module_name": module.module_name,
                "source_file": str(module.source_file),
                "stub_file": str(module.stub_file),
                "typing_imports": list(module.typing_imports),
                "module_imports": list(module.module_imports),
                "symbols": [
                    {
                        "qualname": symbol.qualname,
                        "function_name": symbol.function_name,
                        "class_name": symbol.class_name,
                        "rendered_signatures": list(symbol.rendered_signatures),
                    }
                    for symbol in module.symbols
                ],
            }
            for module in plan.modules
        ]
    }
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_plan_json(file_path: Path) -> TransformPlan:
    """Read a transform plan from JSON.

    Args:
        file_path: JSON plan path.

    Returns:
        Parsed transform plan object.
    """
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    modules = []
    for module_data in payload["modules"]:
        symbols = tuple(
            SymbolPlan(
                qualname=symbol_data["qualname"],
                function_name=symbol_data["function_name"],
                class_name=symbol_data["class_name"],
                rendered_signatures=tuple(symbol_data["rendered_signatures"]),
            )
            for symbol_data in module_data["symbols"]
        )
        modules.append(
            ModulePlan(
                module_name=module_data["module_name"],
                source_file=Path(module_data["source_file"]),
                stub_file=Path(module_data["stub_file"]),
                typing_imports=tuple(module_data["typing_imports"]),
                module_imports=tuple(module_data["module_imports"]),
                symbols=symbols,
            )
        )
    return TransformPlan(modules=tuple(modules))
