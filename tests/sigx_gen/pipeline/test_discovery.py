from __future__ import annotations

from pathlib import Path

from sigx_gen.model.signature import ParamKind
from sigx_gen.pipeline.discovery import (
    derive_module_name,
    discover_modules,
    extract_signature_from_node,
)


def _discover_functions(src_root: Path):
    return tuple(function for module in discover_modules(src_root) for function in module.functions)


def test_module_name_derivation() -> None:
    src_root = Path("/tmp/project/src")

    assert derive_module_name(src_root, src_root / "pkg" / "mod.py") == "pkg.mod"
    assert derive_module_name(src_root, src_root / "pkg" / "__init__.py") == "pkg"


def test_discover_top_level_function(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    file_path = pkg / "mod.py"
    file_path.write_text(
        "from x import dec\n\n@dec\ndef run(name: str) -> None:\n    pass\n",
        encoding="utf-8",
    )

    functions = _discover_functions(src_root)

    assert len(functions) == 1
    fn = functions[0]
    assert fn.module_name == "pkg.mod"
    assert fn.qualname == "run"
    assert fn.function_name == "run"
    assert fn.class_name is None
    assert not fn.is_method
    assert len(fn.decorators) == 1


def test_discover_class_method(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    file_path = pkg / "mod.py"
    file_path.write_text(
        'class Jobs:\n    @dec\n    def run(self, name: str = "x") -> None:\n        pass\n',
        encoding="utf-8",
    )

    functions = _discover_functions(src_root)

    assert len(functions) == 1
    fn = functions[0]
    assert fn.class_name == "Jobs"
    assert fn.qualname == "Jobs.run"
    assert fn.is_method


def test_extract_annotations_defaults_and_async(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    file_path = pkg / "mod.py"
    file_path.write_text(
        'async def run(a: int, /, b: str = "x", *args: int, c: bool = True, **kwargs: object) -> None:\n    pass\n',
        encoding="utf-8",
    )

    function = _discover_functions(src_root)[0]
    sig = extract_signature_from_node(function.node)

    assert function.is_async
    assert sig.is_async
    assert sig.return_annotation == "None"
    assert [p.kind for p in sig.params] == [
        ParamKind.POS_ONLY,
        ParamKind.POS_OR_KW,
        ParamKind.VAR_POS,
        ParamKind.KW_ONLY,
        ParamKind.VAR_KW,
    ]
    assert sig.params[0].annotation == "int"
    assert sig.params[1].default == "'x'"
    assert sig.params[2].annotation == "int"
    assert sig.params[3].default == "True"


def test_discovery_extracts_function_type_params(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    file_path = pkg / "mod.py"
    file_path.write_text(
        ("def run[T: pkg.types.Bound = pkg.types.Default](x: T) -> T:\n    return x\n"),
        encoding="utf-8",
    )

    function = _discover_functions(src_root)[0]
    sig = extract_signature_from_node(function.node)

    assert sig.type_params == ("T: pkg.types.Bound = pkg.types.Default",)


def test_discovery_collects_type_checking_imports(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    pkg = src_root / "pkg"
    pkg.mkdir(parents=True)
    file_path = pkg / "mod.py"
    file_path.write_text(
        (
            "from typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n"
            "    from pkga.types import Model\n"
            "\n"
            "def run(x: Model) -> None:\n"
            "    pass\n"
        ),
        encoding="utf-8",
    )

    module = discover_modules(src_root)[0]
    assert "from pkga.types import Model" in module.import_statements
