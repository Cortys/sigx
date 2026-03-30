from __future__ import annotations

from pathlib import Path

from sigx_gen.model.symbols import DiscoveredVariable, ImportAlias


def test_symbol_models_construct() -> None:
    alias = ImportAlias(local_name="pm", resolved_module="pkg.mod", resolved_attr=None)
    variable = DiscoveredVariable(name="VALUE", annotation="int")

    assert alias.local_name == "pm"
    assert variable.annotation == "int"
    assert Path("x.py").suffix == ".py"
