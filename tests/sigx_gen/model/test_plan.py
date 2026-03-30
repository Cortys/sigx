from __future__ import annotations

from pathlib import Path

from sigx_gen.model.plan import ModulePlan, SymbolPlan, TransformPlan


def test_plan_models_construct() -> None:
    symbol = SymbolPlan(
        qualname="run",
        function_name="run",
        class_name=None,
        rendered_signatures=("(x: int) -> None",),
    )
    module = ModulePlan(
        module_name="pkg.mod",
        source_file=Path("src/pkg/mod.py"),
        stub_file=Path("stubs/pkg/mod.pyi"),
        typing_imports=("Any",),
        module_imports=("pkga",),
        symbols=(symbol,),
    )
    plan = TransformPlan(modules=(module,))

    assert plan.modules[0].symbols[0].qualname == "run"
