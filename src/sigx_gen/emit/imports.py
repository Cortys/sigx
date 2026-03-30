"""Import synthesis helpers for generated and patched stubs."""

from __future__ import annotations

import ast
import builtins

from sigx_gen.model.signature import SignatureIR

_BUILTIN_NAMES = set(dir(builtins))


def collect_missing_module_imports(
    signatures: tuple[SignatureIR, ...],
    *,
    imported_names: set[str],
    local_symbol_names: set[str],
) -> tuple[str, ...]:
    """Collect missing top-level module imports required by signatures.

    Args:
        signatures: Signatures rendered in a module or symbol plan.
        imported_names: Names already imported in module scope.
        local_symbol_names: Names defined locally in module scope.

    Returns:
        Root module names that should be imported with ``import <name>``.
    """
    dotted_roots: set[str] = set()
    for signature in signatures:
        _, signature_dotted_roots = _collect_signature_name_usage(signature)
        dotted_roots.update(signature_dotted_roots)

    blocked_names = imported_names | local_symbol_names | _BUILTIN_NAMES | {"typing"}
    missing = sorted(root for root in dotted_roots if root not in blocked_names)
    return tuple(missing)


def collect_imported_names(import_statements: tuple[str, ...]) -> set[str]:
    """Collect local import binding names from import statements.

    Args:
        import_statements: Import statements rendered from source.

    Returns:
        Set of locally bound names.
    """
    imported_names: set[str] = set()
    for statement in import_statements:
        parsed = ast.parse(statement)
        for node in parsed.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        imported_names.add(alias.asname or alias.name)
    return imported_names


def _collect_signature_name_usage(signature: SignatureIR) -> tuple[set[str], set[str]]:
    bare_names: set[str] = set()
    dotted_roots: set[str] = set()
    for param in signature.params:
        param_bare, param_dotted = _collect_expr_name_usage(param.annotation)
        bare_names.update(param_bare)
        dotted_roots.update(param_dotted)

        default_bare, default_dotted = _collect_expr_name_usage(param.default)
        bare_names.update(default_bare)
        dotted_roots.update(default_dotted)

    return_bare, return_dotted = _collect_expr_name_usage(signature.return_annotation)
    bare_names.update(return_bare)
    dotted_roots.update(return_dotted)
    return bare_names, dotted_roots


def _collect_expr_name_usage(expr: str | None) -> tuple[set[str], set[str]]:
    if expr is None:
        return set(), set()

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return set(), set()

    bare_names: set[str] = set()
    dotted_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            bare_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            root = _attribute_root_name(node)
            if root is not None:
                dotted_roots.add(root)
    return bare_names, dotted_roots


def _attribute_root_name(node: ast.Attribute) -> str | None:
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return None
