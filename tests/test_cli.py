from __future__ import annotations

from pathlib import Path
import shutil

from sigx_gen.cli import run_generate
from sigx_gen.config import GenerationConfig


def _copy_fixture_src(tmp_path: Path) -> Path:
    fixture_root = Path(__file__).parent.parent / "fixtures" / "project_basic" / "src"
    work_src = tmp_path / "src"
    shutil.copytree(fixture_root, work_src)
    for stub_path in work_src.rglob("*.pyi"):
        stub_path.unlink()
    return work_src


def test_generate_writes_stubs(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=False))

    assert code == 0
    assert (work_src / "myproj" / "jobs.pyi").exists()


def test_check_reports_mismatch_and_then_success(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)

    mismatch_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=True))
    assert mismatch_code == 1

    generate_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=False))
    assert generate_code == 0

    check_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=True))
    assert check_code == 0
