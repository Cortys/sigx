from __future__ import annotations

from pathlib import Path
import shutil

from sigx_gen.cli import run_generate, run_patch
from sigx_gen.config import GenerationConfig, PatchConfig


def _copy_fixture_src(tmp_path: Path) -> Path:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "project_basic" / "src"
    work_src = tmp_path / "src"
    shutil.copytree(fixture_root, work_src)
    for stub_path in work_src.rglob("*.pyi"):
        stub_path.unlink()
    return work_src


def _write_baseline_jobs_stub(work_src: Path) -> None:
    jobs_stub = work_src / "myproj" / "jobs.pyi"
    jobs_stub.parent.mkdir(parents=True, exist_ok=True)
    jobs_stub.write_text(
        (
            "MAX_RETRIES: int\n\n"
            "def run_job(name: str) -> None: ...\n\n"
            "def helper(payload: Payload) -> int: ...\n\n"
            "class Payload: ...\n\n"
            "class Worker:\n"
            "    def process(self, name: str) -> None: ...\n\n"
            "    def ping(self, payload: Payload) -> int: ...\n"
        ),
        encoding="utf-8",
    )


def test_generate_writes_stubs(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)

    code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=False))

    assert code == 0
    assert (work_src / "myproj" / "jobs.pyi").exists()
    content = (work_src / "myproj" / "jobs.pyi").read_text(encoding="utf-8")
    assert "debug: Any = ..." in content
    assert "trace: Any = ..." in content
    assert "attempt: Any = ..." in content
    assert not (work_src / "myproj" / "util.pyi").exists()


def test_check_reports_mismatch_and_then_success(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)

    mismatch_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=True))
    assert mismatch_code == 1

    generate_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=False))
    assert generate_code == 0

    check_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=True))
    assert check_code == 0


def test_patch_updates_existing_stubs(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    _write_baseline_jobs_stub(work_src)

    code = run_patch(PatchConfig(src_root=work_src, stub_root=work_src, check=False))

    assert code == 0
    content = (work_src / "myproj" / "jobs.pyi").read_text(encoding="utf-8")
    assert "debug: Any = ..." in content
    assert "trace: Any = ..." in content
    assert "attempt: Any = ..." in content


def test_generate_prunes_unplanned_stubs(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    unplanned_stub = work_src / "myproj" / "unused.pyi"
    unplanned_stub.write_text("def unused() -> None: ...\n", encoding="utf-8")

    code = run_generate(
        GenerationConfig(
            src_root=work_src,
            out_root=work_src,
            check=False,
        )
    )

    assert code == 0
    assert not unplanned_stub.exists()


def test_generate_check_prune_reports_unplanned_as_drift(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=False))
    unplanned_stub = work_src / "myproj" / "unused.pyi"
    unplanned_stub.write_text("def unused() -> None: ...\n", encoding="utf-8")

    code = run_generate(
        GenerationConfig(
            src_root=work_src,
            out_root=work_src,
            check=True,
        )
    )

    assert code == 1
    assert unplanned_stub.exists()


def test_generate_check_does_not_mutate_existing_stubs(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    _write_baseline_jobs_stub(work_src)

    code = run_generate(
        GenerationConfig(
            src_root=work_src,
            out_root=work_src,
            check=True,
        )
    )

    assert code == 1
    content = (work_src / "myproj" / "jobs.pyi").read_text(encoding="utf-8")
    assert "debug: Any = ..." not in content


def test_generate_prunes_init_stubs_when_out_is_src(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)

    code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=False))

    assert code == 0
    assert (work_src / "myproj" / "jobs.pyi").exists()
    assert not (work_src / "myproj" / "__init__.pyi").exists()
    assert not (work_src / "myproj" / "util.pyi").exists()


def test_generate_keeps_required_init_stubs_when_out_differs(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    out_root = tmp_path / "stubs"

    code = run_generate(GenerationConfig(src_root=work_src, out_root=out_root, check=False))

    assert code == 0
    assert (out_root / "myproj" / "jobs.pyi").exists()
    assert (out_root / "myproj" / "__init__.pyi").exists()
    assert not (out_root / "myproj" / "util.pyi").exists()


def test_generate_out_of_src_prunes_init_without_source_package_init(tmp_path: Path) -> None:
    work_src = _copy_fixture_src(tmp_path)
    (work_src / "myproj" / "__init__.py").unlink()
    out_root = tmp_path / "stubs"

    code = run_generate(GenerationConfig(src_root=work_src, out_root=out_root, check=False))

    assert code == 0
    assert (out_root / "myproj" / "jobs.pyi").exists()
    assert not (out_root / "myproj" / "__init__.pyi").exists()
