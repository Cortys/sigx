from __future__ import annotations

from collections.abc import Iterator
import importlib
from pathlib import Path
import sys
import uuid

import pytest

from sigx_gen.discovery import discover_functions
from sigx_gen.engine import apply_transforms
from sigx_gen.signature_ir import ParamKind


@pytest.fixture
def fixture_project(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    package_name = f"fixturepkg_{uuid.uuid4().hex[:8]}"
    src_root = tmp_path / "src"
    package_dir = src_root / package_name
    package_dir.mkdir(parents=True)

    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "decorators.py").write_text(
        (
            "from sigx import stub_transform\n"
            "from sigx import stub_transform_factory\n\n"
            f'@stub_transform("{package_name}.stub_transforms:add_plain_kwonly")\n'
            "def plain_dec(func):\n"
            "    return func\n\n"
            f'@stub_transform("{package_name}.stub_transforms:add_either_kwonly")\n'
            "def either_dec(func):\n"
            "    return func\n\n"
            f'@stub_transform_factory("{package_name}.stub_transforms:add_factory_kwargs")\n'
            "def add_kwargs(kwarg_list):\n"
            "    def decorator(func):\n"
            "        return func\n"
            "    return decorator\n\n"
            "def regular(func):\n"
            "    return func\n\n"
            f'@stub_transform("{package_name}.stub_transforms:broken_transform")\n'
            "def broken(func):\n"
            "    return func\n"
            f'@stub_transform("{package_name}.stub_transforms:invalid_empty_transform")\n'
            "def invalid_empty(func):\n"
            "    return func\n\n"
            f'@stub_transform("{package_name}.stub_transforms:invalid_item_transform")\n'
            "def invalid_item(func):\n"
            "    return func\n"
        ),
        encoding="utf-8",
    )
    (package_dir / "stub_transforms.py").write_text(
        (
            "from sigx_gen.builder import SignatureBuilder\n\n"
            "def add_plain_kwonly(ctx):\n"
            "    builder = SignatureBuilder.from_signature(ctx.original)\n"
            '    builder.add_kwonly("plain", annotation="Any", default="...")\n'
            "    return builder.build()\n\n"
            "def add_factory_kwargs(ctx):\n"
            "    builder = SignatureBuilder.from_signature(ctx.original)\n"
            '    for name in ctx.bound_factory_args.arguments["kwarg_list"]:\n'
            '        builder.add_kwonly(name, annotation="Any", default="...")\n'
            "    return builder.build()\n\n"
            "def add_either_kwonly(ctx):\n"
            "    option_a = SignatureBuilder.from_signature(ctx.original)\n"
            '    option_a.add_kwonly("a", annotation="Any", default="...")\n'
            "    option_b = SignatureBuilder.from_signature(ctx.original)\n"
            '    option_b.add_kwonly("b", annotation="Any", default="...")\n'
            "    return [option_a.build(), option_b.build()]\n\n"
            "def invalid_empty_transform(ctx):\n"
            "    return []\n\n"
            "def invalid_item_transform(ctx):\n"
            "    return [ctx.original, 42]\n\n"
            "def broken_transform(ctx):\n"
            '    raise RuntimeError("boom")\n'
        ),
        encoding="utf-8",
    )
    (package_dir / "jobs.py").write_text(
        (
            f"from {package_name}.decorators import add_kwargs\n"
            f"from {package_name}.decorators import broken\n"
            f"from {package_name}.decorators import either_dec\n"
            f"from {package_name}.decorators import invalid_empty\n"
            f"from {package_name}.decorators import invalid_item\n"
            f"from {package_name}.decorators import plain_dec\n"
            f"from {package_name}.decorators import regular\n\n"
            "@plain_dec\n"
            "def plain_job(name: str) -> None:\n"
            "    pass\n\n"
            '@add_kwargs(["debug", "trace"])\n'
            "def factory_job(name: str) -> None:\n"
            "    pass\n\n"
            '@add_kwargs(["top"])\n'
            '@add_kwargs(["bottom"])\n'
            "def ordered_job(name: str) -> None:\n"
            "    pass\n\n"
            "@plain_dec\n"
            "@either_dec\n"
            "def branching_job(name: str) -> None:\n"
            "    pass\n\n"
            "@regular\n"
            "def no_meta(name: str) -> None:\n"
            "    pass\n\n"
            "@broken\n"
            "def broken_job(name: str) -> None:\n"
            "    pass\n\n"
            "@invalid_empty\n"
            "def invalid_empty_job(name: str) -> None:\n"
            "    pass\n\n"
            "@invalid_item\n"
            "def invalid_item_job(name: str) -> None:\n"
            "    pass\n"
        ),
        encoding="utf-8",
    )

    sys.path.insert(0, str(src_root))
    importlib.invalidate_caches()
    try:
        yield src_root, package_name
    finally:
        if str(src_root) in sys.path:
            sys.path.remove(str(src_root))


def test_plain_decorator_transform_applied(fixture_project: tuple[Path, str]) -> None:
    src_root, package_name = fixture_project
    discovered = discover_functions(src_root)

    result = apply_transforms(discovered)
    signatures = {
        item.function_name: item.signatures for item in result.functions if item.module_name == f"{package_name}.jobs"
    }

    assert "plain_job" in signatures
    assert signatures["plain_job"][0].has_param("plain")
    plain_param = signatures["plain_job"][0].get_param("plain")
    assert plain_param is not None
    assert plain_param.kind == ParamKind.KW_ONLY


def test_decorator_factory_transform_applied(fixture_project: tuple[Path, str]) -> None:
    src_root, package_name = fixture_project
    discovered = discover_functions(src_root)

    result = apply_transforms(discovered)
    signatures = {
        item.function_name: item.signatures for item in result.functions if item.module_name == f"{package_name}.jobs"
    }

    assert signatures["factory_job"][0].has_param("debug")
    assert signatures["factory_job"][0].has_param("trace")


def test_multiple_transforms_apply_in_source_order(fixture_project: tuple[Path, str]) -> None:
    src_root, package_name = fixture_project
    discovered = discover_functions(src_root)

    result = apply_transforms(discovered)
    ordered = {
        item.function_name: item.signatures for item in result.functions if item.module_name == f"{package_name}.jobs"
    }["ordered_job"][0]

    names = [param.name for param in ordered.params if param.kind == ParamKind.KW_ONLY]
    assert names == ["bottom", "top"]


def test_cross_product_branching_respects_bottom_to_top_order(fixture_project: tuple[Path, str]) -> None:
    src_root, package_name = fixture_project
    discovered = discover_functions(src_root)

    result = apply_transforms(discovered)
    branched = {
        item.function_name: item.signatures for item in result.functions if item.module_name == f"{package_name}.jobs"
    }["branching_job"]

    assert len(branched) == 2
    branch_kwonly_names = [
        [param.name for param in signature.params if param.kind == ParamKind.KW_ONLY] for signature in branched
    ]
    assert branch_kwonly_names == [["a", "plain"], ["b", "plain"]]


def test_decorator_without_metadata_is_ignored(fixture_project: tuple[Path, str]) -> None:
    src_root, package_name = fixture_project
    discovered = discover_functions(src_root)

    result = apply_transforms(discovered)
    function_names = {item.function_name for item in result.functions if item.module_name == f"{package_name}.jobs"}

    assert "no_meta" not in function_names


def test_transform_callback_failure_recorded(fixture_project: tuple[Path, str]) -> None:
    src_root, package_name = fixture_project
    discovered = discover_functions(src_root)

    result = apply_transforms(discovered)

    assert any(
        diagnostic.code == "SX007"
        and diagnostic.module_name == f"{package_name}.jobs"
        and diagnostic.qualname == "broken_job"
        for diagnostic in result.diagnostics
    )


def test_invalid_transform_results_recorded(fixture_project: tuple[Path, str]) -> None:
    src_root, package_name = fixture_project
    discovered = discover_functions(src_root)

    result = apply_transforms(discovered)

    assert any(
        diagnostic.code == "SX008"
        and diagnostic.module_name == f"{package_name}.jobs"
        and diagnostic.qualname == "invalid_empty_job"
        for diagnostic in result.diagnostics
    )
    assert any(
        diagnostic.code == "SX008"
        and diagnostic.module_name == f"{package_name}.jobs"
        and diagnostic.qualname == "invalid_item_job"
        for diagnostic in result.diagnostics
    )
