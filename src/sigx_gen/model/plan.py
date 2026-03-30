"""Serializable plan model for patch-based stub updates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SymbolPlan:
    """Plan entry for one symbol override in a module stub.

    Attributes:
        qualname: Symbol qualname (``Class.method`` or ``function``).
        function_name: Function or method name.
        class_name: Owning class name if method.
        rendered_signatures: Rendered signatures for function definition(s).
    """

    qualname: str
    function_name: str
    class_name: str | None
    rendered_signatures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModulePlan:
    """Patch plan for one module stub file.

    Attributes:
        module_name: Module dotted path.
        source_file: Source module file path.
        stub_file: Target stub file path.
        typing_imports: Required symbols imported from ``typing``.
        module_imports: Required ``import X`` statements.
        symbols: Symbols to replace or insert.
    """

    module_name: str
    source_file: Path
    stub_file: Path
    typing_imports: tuple[str, ...]
    module_imports: tuple[str, ...]
    symbols: tuple[SymbolPlan, ...]


@dataclass(frozen=True, slots=True)
class TransformPlan:
    """Aggregate plan used to patch existing stubs.

    Attributes:
        modules: Module plans with transformed symbol updates.
    """

    modules: tuple[ModulePlan, ...]
