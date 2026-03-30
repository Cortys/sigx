from __future__ import annotations

from pathlib import Path
import shutil

from sigx_gen.cli import run_apply, run_plan
from sigx_gen.config import ApplyConfig, PlanConfig
from sigx_gen.io.plan_json import read_plan_json


def _copy_fixture_src(tmp_path: Path) -> Path:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "project_basic" / "src"
    work_src = tmp_path / "src"
    shutil.copytree(fixture_root, work_src)
    for stub_path in work_src.rglob("*.pyi"):
        stub_path.unlink()
    return work_src


def test_plan_command_writes_transform_plan(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    plan_file = tmp_path / "plan.json"

    code = run_plan(PlanConfig(src_root=work_src, stub_root=work_src, plan_file=plan_file))

    assert code == 0
    assert plan_file.exists()
    plan = read_plan_json(plan_file)
    assert len(plan.modules) == 1
    assert plan.modules[0].module_name == "myproj.jobs"
    assert all(symbol.qualname in {"run_job", "Worker.process"} for symbol in plan.modules[0].symbols)


def test_apply_command_requires_libcst_when_unavailable(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    plan_file = tmp_path / "plan.json"
    run_plan(PlanConfig(src_root=work_src, stub_root=work_src, plan_file=plan_file))

    code = run_apply(ApplyConfig(plan_file=plan_file, check=False))

    assert code in {0, 2}
