from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import sys
import uuid

from sigx_gen.model.plan import TransformPlan
from sigx_gen.pipeline.discovery import discover_modules
from sigx_gen.pipeline.planner import build_transform_plan
from sigx_gen.pipeline.transformer import apply_transforms


def _build_transform_plan(src_root: Path, *, stub_root: Path) -> TransformPlan:
    sys.path.insert(0, str(src_root))
    importlib.invalidate_caches()
    try:
        modules = discover_modules(src_root)
        discovered = tuple(function for module in modules for function in module.functions)
        transformed = apply_transforms(discovered)
    finally:
        if str(src_root) in sys.path:
            sys.path.remove(str(src_root))

    return build_transform_plan(modules, transformed.functions, src_root=src_root, stub_root=stub_root)


def test_e2e_generate_fixture_project(tmp_path: Path) -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "project_basic" / "src"
    work_src = tmp_path / "src"
    shutil.copytree(fixture_root, work_src)

    plan = _build_transform_plan(work_src, stub_root=work_src)

    assert len(plan.modules) == 1
    module_plan = plan.modules[0]
    assert module_plan.module_name == "myproj.jobs"
    assert module_plan.typing_imports == ("Any",)
    assert module_plan.module_imports == ()
    symbol_signatures = {symbol.qualname: symbol.rendered_signatures for symbol in module_plan.symbols}
    assert symbol_signatures == {
        "Worker.process": ("(self, name: str, *, attempt: Any = ...) -> None",),
        "run_job": ("(name: str, *, debug: Any = ..., trace: Any = ...) -> None",),
    }


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

    plan = _build_transform_plan(src_root, stub_root=src_root)

    assert len(plan.modules) == 1
    module_plan = plan.modules[0]
    assert module_plan.module_name == f"{package_name}.jobs"
    assert module_plan.typing_imports == ("Any", "overload")
    assert module_plan.symbols[0].qualname == "run"
    assert module_plan.symbols[0].rendered_signatures == (
        "(name: str, *, a: Any = ..., trace: Any = ...) -> None",
        "(name: str, *, b: Any = ..., trace: Any = ...) -> None",
    )


def test_e2e_generate_adds_missing_root_import_for_dotted_annotation(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    package_name = f"myproj_{uuid.uuid4().hex[:8]}"
    package = src_root / package_name
    pkga = src_root / "pkga"
    package.mkdir(parents=True)
    pkga.mkdir(parents=True)

    (pkga / "__init__.py").write_text("", encoding="utf-8")
    (pkga / "b.py").write_text("class C:\n    pass\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "decorators.py").write_text(
        (
            "from sigx import stub_transform\n\n"
            f'@stub_transform("{package_name}.stub_transforms:add_c")\n'
            "def add_c(func):\n"
            "    return func\n"
        ),
        encoding="utf-8",
    )
    (package / "stub_transforms.py").write_text(
        (
            "from sigx_gen.builder import SignatureBuilder\n\n"
            "def add_c(ctx):\n"
            "    builder = SignatureBuilder.from_signature(ctx.original)\n"
            '    builder.add_kwonly("c", annotation="pkga.b.C", default="...")\n'
            "    return builder.build()\n"
        ),
        encoding="utf-8",
    )
    (package / "jobs.py").write_text(
        (f"from {package_name}.decorators import add_c\n\n@add_c\ndef run(name: str) -> None:\n    pass\n"),
        encoding="utf-8",
    )

    plan = _build_transform_plan(src_root, stub_root=src_root)

    assert len(plan.modules) == 1
    module_plan = plan.modules[0]
    assert module_plan.module_imports == ("pkga",)
    assert module_plan.symbols[0].rendered_signatures == ("(name: str, *, c: pkga.b.C = ...) -> None",)


def test_e2e_generate_preserves_generic_type_params(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    package_name = f"myproj_{uuid.uuid4().hex[:8]}"
    package = src_root / package_name
    package.mkdir(parents=True)

    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "decorators.py").write_text(
        (
            "from sigx import stub_transform\n\n"
            f'@stub_transform("{package_name}.stub_transforms:add_flag")\n'
            "def add_flag(func):\n"
            "    return func\n"
        ),
        encoding="utf-8",
    )
    (package / "stub_transforms.py").write_text(
        (
            "from sigx_gen.builder import SignatureBuilder\n\n"
            "def add_flag(ctx):\n"
            "    builder = SignatureBuilder.from_signature(ctx.original)\n"
            '    builder.add_kwonly("flag", annotation="Any", default="...")\n'
            "    return builder.build()\n"
        ),
        encoding="utf-8",
    )
    (package / "jobs.py").write_text(
        (
            f"from {package_name}.decorators import add_flag\n\n"
            "@add_flag\n"
            "def run[T](value: T) -> T:\n"
            "    return value\n"
        ),
        encoding="utf-8",
    )

    plan = _build_transform_plan(src_root, stub_root=src_root)

    assert len(plan.modules) == 1
    module_plan = plan.modules[0]
    assert module_plan.typing_imports == ("Any",)
    assert module_plan.symbols[0].rendered_signatures == ("[T](value: T, *, flag: Any = ...) -> T",)


def test_e2e_generate_type_checking_imports_survive(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    package_name = f"myproj_{uuid.uuid4().hex[:8]}"
    package = src_root / package_name
    external = src_root / "external"
    package.mkdir(parents=True)
    external.mkdir(parents=True)

    (external / "__init__.py").write_text("", encoding="utf-8")
    (external / "types.py").write_text("class Model:\n    pass\n", encoding="utf-8")
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
            "    from external.types import Model\n\n"
            "@add_debug\n"
            "def run(model: Model) -> None:\n"
            "    pass\n"
        ),
        encoding="utf-8",
    )

    plan = _build_transform_plan(src_root, stub_root=src_root)

    assert len(plan.modules) == 1
    module_plan = plan.modules[0]
    assert module_plan.typing_imports == ()
    assert module_plan.module_imports == ()
    assert module_plan.symbols[0].rendered_signatures == ("(model: Model, *, debug: bool = False) -> None",)
