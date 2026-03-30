"""AST-based source discovery for decorated functions and methods."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from sigx_gen.signature_ir import ParamKind, SignatureIR, SigParam


@dataclass(frozen=True, slots=True)
class ImportAlias:
    """Imported name alias used for decorator resolution.

    Attributes:
        local_name: Name visible in the module.
        resolved_module: Imported module path, if known.
        resolved_attr: Imported attribute name, if applicable.
    """

    local_name: str
    resolved_module: str | None
    resolved_attr: str | None


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


def derive_module_name(src_root: Path, file_path: Path) -> str:
    """Derive a module name from a source-root-relative path.

    Args:
        src_root: Source root directory.
        file_path: Python source file path.

    Returns:
        Dotted module name.
    """
    relative = file_path.relative_to(src_root)
    parts = relative.parts[:-1] if relative.name == "__init__.py" else (*relative.parts[:-1], relative.stem)
    return ".".join(parts)


def discover_functions(src_root: Path) -> tuple[DiscoveredFunction, ...]:
    """Discover top-level functions and class methods under a source root.

    Args:
        src_root: Root path containing Python source files.

    Returns:
        Discovered function records in deterministic order.
    """
    discovered: list[DiscoveredFunction] = []
    for file_path in sorted(src_root.rglob("*.py")):
        module_name = derive_module_name(src_root=src_root, file_path=file_path)
        module_ast = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        imports = tuple(_collect_import_aliases(module_ast))

        for node in module_ast.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                discovered.append(
                    DiscoveredFunction(
                        module_name=module_name,
                        file_path=file_path,
                        qualname=node.name,
                        function_name=node.name,
                        class_name=None,
                        is_async=isinstance(node, ast.AsyncFunctionDef),
                        is_method=False,
                        decorators=tuple(node.decorator_list),
                        node=node,
                        imports=imports,
                    )
                )
                continue

            if not isinstance(node, ast.ClassDef):
                continue

            discovered.extend(
                DiscoveredFunction(
                    module_name=module_name,
                    file_path=file_path,
                    qualname=f"{node.name}.{class_body_node.name}",
                    function_name=class_body_node.name,
                    class_name=node.name,
                    is_async=isinstance(class_body_node, ast.AsyncFunctionDef),
                    is_method=True,
                    decorators=tuple(class_body_node.decorator_list),
                    node=class_body_node,
                    imports=imports,
                )
                for class_body_node in node.body
                if isinstance(class_body_node, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return tuple(discovered)


def extract_signature_from_node(node: ast.FunctionDef | ast.AsyncFunctionDef) -> SignatureIR:
    """Extract immutable signature IR from a function AST node.

    Args:
        node: Function or async function AST node.

    Returns:
        Extracted signature model.
    """
    args = node.args
    params: list[SigParam] = []

    positional = [*args.posonlyargs, *args.args]
    positional_defaults = args.defaults
    defaults_start = len(positional) - len(positional_defaults)

    for index, arg in enumerate(positional):
        kind = ParamKind.POS_ONLY if index < len(args.posonlyargs) else ParamKind.POS_OR_KW
        default: str | None = None
        if index >= defaults_start:
            default_index = index - defaults_start
            default = ast.unparse(positional_defaults[default_index])
        params.append(
            SigParam(
                name=arg.arg,
                kind=kind,
                annotation=_unparse_or_none(arg.annotation),
                default=default,
            )
        )

    if args.vararg is not None:
        params.append(
            SigParam(
                name=args.vararg.arg,
                kind=ParamKind.VAR_POS,
                annotation=_unparse_or_none(args.vararg.annotation),
                default=None,
            )
        )

    for kwarg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        params.append(
            SigParam(
                name=kwarg.arg,
                kind=ParamKind.KW_ONLY,
                annotation=_unparse_or_none(kwarg.annotation),
                default=_unparse_or_none(kw_default),
            )
        )

    if args.kwarg is not None:
        params.append(
            SigParam(
                name=args.kwarg.arg,
                kind=ParamKind.VAR_KW,
                annotation=_unparse_or_none(args.kwarg.annotation),
                default=None,
            )
        )

    return SignatureIR(
        params=tuple(params),
        return_annotation=_unparse_or_none(node.returns),
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _collect_import_aliases(module_ast: ast.Module) -> list[ImportAlias]:
    aliases: list[ImportAlias] = []
    for statement in module_ast.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                local_name = alias.asname or alias.name.split(".")[0]
                aliases.append(
                    ImportAlias(
                        local_name=local_name,
                        resolved_module=alias.name,
                        resolved_attr=None,
                    )
                )
            continue

        if isinstance(statement, ast.ImportFrom):
            if statement.level != 0 or statement.module is None:
                continue
            for alias in statement.names:
                if alias.name == "*":
                    continue
                aliases.append(
                    ImportAlias(
                        local_name=alias.asname or alias.name,
                        resolved_module=statement.module,
                        resolved_attr=alias.name,
                    )
                )
    return aliases


def _unparse_or_none(value: ast.AST | None) -> str | None:
    if value is None:
        return None
    return ast.unparse(value)
