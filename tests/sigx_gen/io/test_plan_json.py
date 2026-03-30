from __future__ import annotations

from pathlib import Path

from sigx_gen.io.plan_json import read_plan_json, write_plan_json
from sigx_gen.model.plan import ModulePlan, SymbolPlan, TransformPlan


def test_plan_json_roundtrip(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan = TransformPlan(
        modules=(
            ModulePlan(
                module_name="pkg.jobs",
                source_file=Path("src/pkg/jobs.py"),
                stub_file=Path("stubs/pkg/jobs.pyi"),
                typing_imports=("Any", "overload"),
                module_imports=("pkga",),
                symbols=(
                    SymbolPlan(
                        qualname="run",
                        function_name="run",
                        class_name=None,
                        rendered_signatures=("(x: int) -> None",),
                    ),
                ),
            ),
        ),
    )

    write_plan_json(plan, plan_file)
    loaded = read_plan_json(plan_file)

    assert loaded == plan
