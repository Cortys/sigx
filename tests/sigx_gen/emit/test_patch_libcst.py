from __future__ import annotations

from pathlib import Path

from sigx_gen.emit.patch_libcst import build_libcst_backend
from sigx_gen.model.plan import ModulePlan, SymbolPlan


def test_build_libcst_backend_optional_dependency() -> None:
    try:
        backend = build_libcst_backend()
    except RuntimeError:
        assert True
        return

    assert backend is not None


def test_patch_libcst_preserves_docstring_for_replaced_function() -> None:
    try:
        backend = build_libcst_backend()
    except RuntimeError:
        assert True
        return

    existing_text = 'def run(name: str) -> None:\n    """Run one job."""\n    ...\n'
    module_plan = ModulePlan(
        module_name="pkg.mod",
        source_file=Path("src/pkg/mod.py"),
        stub_file=Path("stubs/pkg/mod.pyi"),
        typing_imports=("Any",),
        module_imports=(),
        symbols=(
            SymbolPlan(
                qualname="run",
                function_name="run",
                class_name=None,
                rendered_signatures=("(name: str, *, debug: Any = ...) -> None",),
            ),
        ),
    )

    patched_text, diagnostics = backend.patch_module(existing_text, module_plan)

    assert diagnostics == ()
    assert '"""Run one job."""' in patched_text
    assert "def run(name: str, *, debug: Any = ...) -> None:" in patched_text


def test_patch_libcst_preserves_docstring_on_first_generated_overload() -> None:
    try:
        backend = build_libcst_backend()
    except RuntimeError:
        assert True
        return

    existing_text = 'def run(name: str) -> None:\n    """Run one job."""\n    ...\n'
    module_plan = ModulePlan(
        module_name="pkg.mod",
        source_file=Path("src/pkg/mod.py"),
        stub_file=Path("stubs/pkg/mod.pyi"),
        typing_imports=("Any", "overload"),
        module_imports=(),
        symbols=(
            SymbolPlan(
                qualname="run",
                function_name="run",
                class_name=None,
                rendered_signatures=(
                    "(name: str, *, debug: Any = ...) -> None",
                    "(name: str, *, trace: Any = ...) -> None",
                ),
            ),
        ),
    )

    patched_text, diagnostics = backend.patch_module(existing_text, module_plan)

    assert diagnostics == ()
    assert patched_text.count("@overload") == 2
    assert patched_text.count('"""Run one job."""') == 1
