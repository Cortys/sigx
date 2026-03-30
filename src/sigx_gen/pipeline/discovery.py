"""AST-based source discovery for modules, symbols, and signatures."""

from __future__ import annotations

import ast
from pathlib import Path

from sigx_gen.model.signature import ParamKind, SignatureIR, SigParam
from sigx_gen.model.symbols import DiscoveredFunction, DiscoveredModule, DiscoveredVariable, ImportAlias


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


def discover_modules(src_root: Path) -> tuple[DiscoveredModule, ...]:
    """Discover modules and symbol surfaces from source files.

    Args:
        src_root: Root path containing Python source files.

    Returns:
        Discovered modules in deterministic order.
    """
    modules: list[DiscoveredModule] = []
    for file_path in sorted(src_root.rglob("*.py")):
        module_name = derive_module_name(src_root=src_root, file_path=file_path)
        module_ast = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        imports = tuple(_collect_import_aliases(module_ast))
        import_statements = tuple(_collect_import_statements(module_ast))
        class_names = tuple(node.name for node in module_ast.body if isinstance(node, ast.ClassDef))
        variables = tuple(_collect_variables(module_ast))
        functions = tuple(_collect_functions(module_ast, module_name, file_path, imports))
        modules.append(
            DiscoveredModule(
                module_name=module_name,
                file_path=file_path,
                imports=imports,
                import_statements=import_statements,
                class_names=class_names,
                variables=variables,
                functions=functions,
            )
        )
    return tuple(modules)


def discover_functions(src_root: Path) -> tuple[DiscoveredFunction, ...]:
    """Discover top-level functions and class methods under a source root.

    Args:
        src_root: Root path containing Python source files.

    Returns:
        Discovered function records in deterministic order.
    """
    functions: list[DiscoveredFunction] = []
    for module in discover_modules(src_root):
        functions.extend(module.functions)
    return tuple(functions)


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


def _collect_functions(
    module_ast: ast.Module,
    module_name: str,
    file_path: Path,
    imports: tuple[ImportAlias, ...],
) -> list[DiscoveredFunction]:
    functions: list[DiscoveredFunction] = []
    for node in module_ast.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(
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
                    lineno=node.lineno,
                )
            )
            continue

        if not isinstance(node, ast.ClassDef):
            continue

        functions.extend(
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
                lineno=class_body_node.lineno,
            )
            for class_body_node in node.body
            if isinstance(class_body_node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
    return functions


def _collect_variables(module_ast: ast.Module) -> list[DiscoveredVariable]:
    variables: list[DiscoveredVariable] = []
    for node in module_ast.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            variables.append(
                DiscoveredVariable(
                    name=node.target.id,
                    annotation=_unparse_or_none(node.annotation),
                )
            )
            continue

        if isinstance(node, ast.Assign):
            variables.extend(
                DiscoveredVariable(name=target.id, annotation=None)
                for target in node.targets
                if isinstance(target, ast.Name)
            )
    return variables


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


def _collect_import_statements(module_ast: ast.Module) -> list[str]:
    return [
        ast.unparse(statement) for statement in module_ast.body if isinstance(statement, (ast.Import, ast.ImportFrom))
    ]


def _unparse_or_none(value: ast.AST | None) -> str | None:
    if value is None:
        return None
    return ast.unparse(value)
