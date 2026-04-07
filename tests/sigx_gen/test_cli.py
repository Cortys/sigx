from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from sigx_gen.cli import run_generate, run_patch
from sigx_gen.config import GenerationConfig, PatchConfig
from sigx_gen.emit.patch_base import PatchRunResult


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


def _write_patched_jobs_stub(work_src: Path) -> None:
    jobs_stub = work_src / "myproj" / "jobs.pyi"
    jobs_stub.parent.mkdir(parents=True, exist_ok=True)
    jobs_stub.write_text(
        (
            "from typing import Any\n\n"
            "MAX_RETRIES: int\n\n"
            "def run_job(name: str, *, debug: Any = ..., trace: Any = ...) -> None: ...\n\n"
            "def helper(payload: Payload) -> int: ...\n\n"
            "class Payload: ...\n\n"
            "class Worker:\n"
            "    def process(self, name: str, *, attempt: Any = ...) -> None: ...\n\n"
            "    def ping(self, payload: Payload) -> int: ...\n"
        ),
        encoding="utf-8",
    )


def _install_fake_patcher(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_backend() -> object:
        return object()

    monkeypatch.setattr("sigx_gen.cli.build_libcst_backend", fake_backend)

    def fake_apply_patch_plan(plan, *, backend, check: bool):
        del backend
        stub_path = next(module.stub_file for module in plan.modules if module.module_name == "myproj.jobs")
        current_text = stub_path.read_text(encoding="utf-8")
        wants_patch = "debug: Any = ..." not in current_text
        if check and wants_patch:
            return PatchRunResult(written_paths=(), mismatches=(stub_path,), diagnostics=())
        if wants_patch:
            _write_patched_jobs_stub(stub_path.parents[1])
            return PatchRunResult(written_paths=(stub_path,), mismatches=(), diagnostics=())
        return PatchRunResult(written_paths=(), mismatches=(), diagnostics=())

    monkeypatch.setattr("sigx_gen.cli.apply_patch_plan", fake_apply_patch_plan)


def test_generate_writes_stubs(tmp_path: Path, monkeypatch) -> None:
    work_src = _copy_fixture_src(tmp_path)

    def fake_basedpyright(*, src_root: Path, out_root: Path, module_targets: object) -> None:
        del src_root, module_targets
        _write_baseline_jobs_stub(out_root)

    monkeypatch.setattr("sigx_gen.cli.generate_baseline_stubs", fake_basedpyright)
    _install_fake_patcher(monkeypatch)
    code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=False))

    assert code == 0
    assert (work_src / "myproj" / "jobs.pyi").exists()
    content = (work_src / "myproj" / "jobs.pyi").read_text(encoding="utf-8")
    assert "debug: Any = ..." in content
    assert "trace: Any = ..." in content
    assert "attempt: Any = ..." in content
    assert not (work_src / "myproj" / "util.pyi").exists()


def test_check_reports_mismatch_and_then_success(tmp_path: Path, monkeypatch) -> None:
    work_src = _copy_fixture_src(tmp_path)

    def fake_basedpyright(*, src_root: Path, out_root: Path, module_targets: object) -> None:
        del src_root, module_targets
        jobs_stub = out_root / "myproj" / "jobs.pyi"
        if not jobs_stub.exists():
            _write_baseline_jobs_stub(out_root)

    monkeypatch.setattr("sigx_gen.cli.generate_baseline_stubs", fake_basedpyright)
    _install_fake_patcher(monkeypatch)

    mismatch_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=True))
    assert mismatch_code == 1

    generate_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=False))
    assert generate_code == 0

    check_code = run_generate(GenerationConfig(src_root=work_src, out_root=work_src, check=True))
    assert check_code == 0


def test_patch_updates_existing_stubs(tmp_path: Path, monkeypatch) -> None:
    work_src = _copy_fixture_src(tmp_path)
    _write_baseline_jobs_stub(work_src)
    _install_fake_patcher(monkeypatch)

    code = run_patch(PatchConfig(src_root=work_src, stub_root=work_src, check=False))

    assert code == 0
    content = (work_src / "myproj" / "jobs.pyi").read_text(encoding="utf-8")
    assert "debug: Any = ..." in content
    assert "trace: Any = ..." in content
    assert "attempt: Any = ..." in content


def test_generate_prunes_unplanned_stubs(tmp_path: Path, monkeypatch) -> None:
    work_src = _copy_fixture_src(tmp_path)
    _write_baseline_jobs_stub(work_src)
    unplanned_stub = work_src / "myproj" / "unused.pyi"
    unplanned_stub.write_text("def unused() -> None: ...\n", encoding="utf-8")

    def fake_basedpyright(*, src_root: Path, out_root: Path, module_targets: object) -> None:
        del src_root, module_targets
        _write_baseline_jobs_stub(out_root)

    monkeypatch.setattr("sigx_gen.cli.generate_baseline_stubs", fake_basedpyright)
    _install_fake_patcher(monkeypatch)

    code = run_generate(
        GenerationConfig(
            src_root=work_src,
            out_root=work_src,
            check=False,
            prune_unplanned=True,
        )
    )

    assert code == 0
    assert not unplanned_stub.exists()


def test_generate_check_prune_reports_unplanned_as_drift(tmp_path: Path, monkeypatch) -> None:
    work_src = _copy_fixture_src(tmp_path)
    _write_patched_jobs_stub(work_src)
    unplanned_stub = work_src / "myproj" / "unused.pyi"
    unplanned_stub.write_text("def unused() -> None: ...\n", encoding="utf-8")

    def fake_basedpyright(*, src_root: Path, out_root: Path, module_targets: object) -> None:
        del src_root, module_targets
        jobs_stub = out_root / "myproj" / "jobs.pyi"
        if not jobs_stub.exists():
            _write_patched_jobs_stub(out_root)

    monkeypatch.setattr("sigx_gen.cli.generate_baseline_stubs", fake_basedpyright)
    _install_fake_patcher(monkeypatch)

    code = run_generate(
        GenerationConfig(
            src_root=work_src,
            out_root=work_src,
            check=True,
            prune_unplanned=True,
        )
    )

    assert code == 1
    assert unplanned_stub.exists()


def test_generate_check_does_not_mutate_existing_stubs(tmp_path: Path, monkeypatch) -> None:
    work_src = _copy_fixture_src(tmp_path)
    _write_baseline_jobs_stub(work_src)

    def fake_basedpyright(*, src_root: Path, out_root: Path, module_targets: object) -> None:
        del src_root, module_targets
        _write_patched_jobs_stub(out_root)

    monkeypatch.setattr("sigx_gen.cli.generate_baseline_stubs", fake_basedpyright)
    _install_fake_patcher(monkeypatch)

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
