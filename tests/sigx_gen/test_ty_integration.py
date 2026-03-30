from __future__ import annotations

import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from sigx_gen.emit.standalone import render_standalone_outputs, write_outputs
from sigx_gen.pipeline.discovery import discover_modules
from sigx_gen.pipeline.transformer import apply_transforms


def _generate_standalone_stubs(src_root: Path) -> None:
    modules = discover_modules(src_root)
    discovered = tuple(function for module in modules for function in module.functions)
    transformed = apply_transforms(discovered)
    outputs = render_standalone_outputs(modules, transformed.functions, src_root=src_root, out_root=src_root)
    write_outputs(outputs)


def _run_ty(src_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ty", "check", str(src_root)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(src_root)},
    )


def test_generated_stubs_are_usable_by_ty(tmp_path: Path) -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "project_basic" / "src"
    work_src = tmp_path / "src"
    shutil.copytree(fixture_root, work_src)

    (work_src / "consumer.py").write_text(
        (
            "from myproj.jobs import Worker\n"
            "from myproj.jobs import run_job\n\n"
            'run_job("job", debug=True, trace=False)\n'
            "worker = Worker()\n"
            'worker.process("job", attempt=1)\n'
        ),
        encoding="utf-8",
    )

    sys.path.insert(0, str(work_src))
    importlib.invalidate_caches()
    try:
        _generate_standalone_stubs(work_src)
    finally:
        if str(work_src) in sys.path:
            sys.path.remove(str(work_src))

    result = _run_ty(work_src)

    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_stubs_with_generics_and_type_only_imports_pass_ty(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    package_name = f"myproj_{uuid.uuid4().hex[:8]}"
    package = src_root / package_name
    ext = src_root / "ext"
    package.mkdir(parents=True)
    ext.mkdir(parents=True)

    (ext / "__init__.py").write_text("", encoding="utf-8")
    (ext / "types.py").write_text("class Bound:\n    pass\n\nclass Model:\n    pass\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "decorators.py").write_text(
        (
            "from sigx import stub_transform\n\n"
            f'@stub_transform("{package_name}.stub_transforms:add_debug")\n'
            "def add_debug(func):\n"
            "    return func\n"
        ),
        encoding="utf-8",
    )
    (package / "stub_transforms.py").write_text(
        (
            "from sigx_gen.builder import SignatureBuilder\n\n"
            "def add_debug(ctx):\n"
            "    builder = SignatureBuilder.from_signature(ctx.original)\n"
            '    builder.add_kwonly("debug", annotation="bool", default="False")\n'
            "    return builder.build()\n"
        ),
        encoding="utf-8",
    )
    (package / "jobs.py").write_text(
        (
            "from typing import TYPE_CHECKING\n"
            f"from {package_name}.decorators import add_debug\n\n"
            "if TYPE_CHECKING:\n"
            "    from ext.types import Bound\n"
            "    from ext.types import Model\n"
            "\n"
            "@add_debug\n"
            "def run[T: Bound](value: T, model: Model) -> T:\n"
            "    return value\n"
        ),
        encoding="utf-8",
    )
    (src_root / "consumer.py").write_text(
        (
            "from ext.types import Bound\n"
            "from ext.types import Model\n"
            f"from {package_name}.jobs import run\n\n"
            "bound = Bound()\n"
            "model = Model()\n"
            "run(bound, model, debug=True)\n"
        ),
        encoding="utf-8",
    )

    sys.path.insert(0, str(src_root))
    importlib.invalidate_caches()
    try:
        _generate_standalone_stubs(src_root)
    finally:
        if str(src_root) in sys.path:
            sys.path.remove(str(src_root))

    result = _run_ty(src_root)

    assert result.returncode == 0, result.stdout + result.stderr
