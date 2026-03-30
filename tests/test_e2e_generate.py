from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import sys
import uuid

from sigx_gen.discovery import discover_functions
from sigx_gen.engine import apply_transforms
from sigx_gen.writer import render_module_outputs, write_module_outputs


def test_e2e_generate_fixture_project(tmp_path: Path) -> None:
    fixture_root = Path(__file__).parent.parent / "fixtures" / "project_basic" / "src"
    work_src = tmp_path / "src"
    shutil.copytree(fixture_root, work_src)

    sys.path.insert(0, str(work_src))
    importlib.invalidate_caches()
    try:
        discovered = discover_functions(work_src)
        result = apply_transforms(discovered)
        outputs = render_module_outputs(result.functions, src_root=work_src, out_root=work_src)
        write_module_outputs(outputs)
    finally:
        if str(work_src) in sys.path:
            sys.path.remove(str(work_src))

    jobs_stub_path = work_src / "myproj" / "jobs.pyi"
    assert jobs_stub_path.exists()
    assert jobs_stub_path.read_text(encoding="utf-8") == (
        "from typing import Any\n\n"
        "def run_job(name: str, *, debug: Any = ..., trace: Any = ...) -> None: ...\n\n"
        "class Worker:\n"
        "    def process(self, name: str, *, attempt: Any = ...) -> None: ...\n"
    )


def test_e2e_generate_overloads_from_branching_transform(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    package_name = f"myproj_{uuid.uuid4().hex[:8]}"
    package = src_root / package_name
    package.mkdir(parents=True)

    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "decorators.py").write_text(
        (
            "from sigx import stub_transform\n\n"
            f'@stub_transform("{package_name}.stub_transforms:either_ab")\n'
            "def either_ab(func):\n"
            "    return func\n\n"
            f'@stub_transform("{package_name}.stub_transforms:add_trace")\n'
            "def add_trace(func):\n"
            "    return func\n"
        ),
        encoding="utf-8",
    )
    (package / "stub_transforms.py").write_text(
        (
            "from sigx_gen.builder import SignatureBuilder\n\n"
            "def either_ab(ctx):\n"
            "    option_a = SignatureBuilder.from_signature(ctx.original)\n"
            '    option_a.add_kwonly("a", annotation="Any", default="...")\n'
            "    option_b = SignatureBuilder.from_signature(ctx.original)\n"
            '    option_b.add_kwonly("b", annotation="Any", default="...")\n'
            "    return [option_a.build(), option_b.build()]\n\n"
            "def add_trace(ctx):\n"
            "    builder = SignatureBuilder.from_signature(ctx.original)\n"
            '    builder.add_kwonly("trace", annotation="Any", default="...")\n'
            "    return builder.build()\n"
        ),
        encoding="utf-8",
    )
    (package / "jobs.py").write_text(
        (
            f"from {package_name}.decorators import add_trace\n"
            f"from {package_name}.decorators import either_ab\n\n"
            "@add_trace\n"
            "@either_ab\n"
            "def run(name: str) -> None:\n"
            "    pass\n"
        ),
        encoding="utf-8",
    )

    sys.path.insert(0, str(src_root))
    importlib.invalidate_caches()
    try:
        discovered = discover_functions(src_root)
        result = apply_transforms(discovered)
        outputs = render_module_outputs(result.functions, src_root=src_root, out_root=src_root)
        write_module_outputs(outputs)
    finally:
        if str(src_root) in sys.path:
            sys.path.remove(str(src_root))

    jobs_stub_path = src_root / package_name / "jobs.pyi"
    assert jobs_stub_path.read_text(encoding="utf-8") == (
        "from typing import Any, overload\n\n"
        "@overload\n"
        "def run(name: str, *, a: Any = ..., trace: Any = ...) -> None: ...\n"
        "@overload\n"
        "def run(name: str, *, b: Any = ..., trace: Any = ...) -> None: ...\n"
    )
