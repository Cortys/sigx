"""Discovery models for source modules and symbols."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ImportAlias:
    """Imported name alias used for decorator and annotation resolution.

    Attributes:
        local_name: Name visible in the module.
        resolved_module: Imported module path, if known.
        resolved_attr: Imported attribute name, if applicable.
    """

    local_name: str
    resolved_module: str | None
    resolved_attr: str | None


@dataclass(frozen=True, slots=True)
class DiscoveredVariable:
    """Top-level variable discovered from source.

    Attributes:
        name: Variable name.
        annotation: Declared annotation source string, if available.
    """

    name: str
    annotation: str | None


@dataclass(frozen=True, slots=True)
class DiscoveredFunction:
    """Function or method discovered from source AST.

    Attributes:
        module_name: Python module path for the source file.
        file_path: Source file path.
        qualname: Function qualname.
        function_name: Function name.
        class_name: Owning class name if method.
        is_async: Whether function is async.
        is_method: Whether function belongs to a class.
        decorators: Raw decorator AST expressions.
        node: AST function node.
        imports: Import aliases captured for module-level resolution.
        lineno: Source line number used for deterministic ordering.
    """

    module_name: str
    file_path: Path
    qualname: str
    function_name: str
    class_name: str | None
    is_async: bool
    is_method: bool
    decorators: tuple[ast.expr, ...]
    node: ast.FunctionDef | ast.AsyncFunctionDef
    imports: tuple[ImportAlias, ...]
    lineno: int


@dataclass(frozen=True, slots=True)
class DiscoveredModule:
    """Source module with discovered public surface elements.

    Attributes:
        module_name: Module dotted path.
        file_path: Source file path.
        imports: Import aliases table.
        import_statements: Import statements from source, including top-level ``TYPE_CHECKING`` blocks.
        class_names: Top-level class names in source order.
        variables: Top-level variables in source order.
        functions: Top-level functions and class methods in source order.
    """

    module_name: str
    file_path: Path
    imports: tuple[ImportAlias, ...]
    import_statements: tuple[str, ...]
    class_names: tuple[str, ...]
    variables: tuple[DiscoveredVariable, ...]
    functions: tuple[DiscoveredFunction, ...]
