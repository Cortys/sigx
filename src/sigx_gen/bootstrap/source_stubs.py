"""Source-driven stub generation helpers."""

from __future__ import annotations

from collections.abc import Iterable
import importlib
from typing import Any

from joblib import Parallel, delayed

from sigx_gen.emit.patch_libcst import patch_module_cst
from sigx_gen.model.diagnostics import Diagnostic
from sigx_gen.model.plan import ModulePlan

_SIGNATURE_NEUTRAL_DECORATOR_WHITELIST = frozenset(
    {
        "typing.override",
        "typing_extensions.override",
    }
)
_SIGNATURE_NEUTRAL_MODULES = frozenset(
    dotted.rsplit(".", maxsplit=1)[0] for dotted in _SIGNATURE_NEUTRAL_DECORATOR_WHITELIST
)


def generate_stubs_from_source(
    *,
    module_plans: Iterable[ModulePlan],
    jobs: int = -1,
) -> tuple[Diagnostic, ...]:
    """Generate and patch stubs from source modules.

    Each module plan is processed in an independent worker. The worker parses the
    source file, builds a minimal base-stub CST, applies the transform plan to
    that CST, and writes the final ``.pyi`` file.

    Args:
        module_plans: Module plans to materialize.
        jobs: Number of parallel workers passed to ``joblib``.

    Returns:
        Diagnostics produced while patching module stubs.
    """
    plans = tuple(module_plans)
    if not plans:
        return ()

    worker_diagnostics = Parallel(n_jobs=jobs)(
        delayed(_generate_one_module_stub)(module_plan=module_plan) for module_plan in plans
    )
    diagnostics: list[Diagnostic] = []
    for module_diagnostics in worker_diagnostics:
        diagnostics.extend(module_diagnostics)
    return tuple(diagnostics)


def _generate_one_module_stub(*, module_plan: ModulePlan) -> tuple[Diagnostic, ...]:
    cst = _import_libcst()
    source_text = module_plan.source_file.read_text(encoding="utf-8")
    source_module = cst.parse_module(source_text)
    neutral_name_aliases, neutral_module_aliases = _collect_signature_neutral_import_aliases(
        module=source_module,
        cst=cst,
    )
    base_stub_module = source_module.visit(
        _build_base_stub_transformer(
            cst=cst,
            neutral_name_aliases=neutral_name_aliases,
            neutral_module_aliases=neutral_module_aliases,
        )
    )
    patched_module, diagnostics = patch_module_cst(
        module=base_stub_module,
        module_plan=module_plan,
        cst=cst,
    )
    module_plan.stub_file.parent.mkdir(parents=True, exist_ok=True)
    module_plan.stub_file.write_text(patched_module.code, encoding="utf-8")
    return diagnostics


def _build_base_stub_transformer(
    *,
    cst: Any,
    neutral_name_aliases: set[str],
    neutral_module_aliases: dict[str, str],
) -> Any:
    class _BaseStubTransformer(cst.CSTTransformer):  # type: ignore[misc]
        """Transform source modules into minimal base-stub modules."""

        def leave_FunctionDef(self, original_node: Any, updated_node: Any) -> Any:
            docstring_statement = _leading_docstring_statement(
                cst=cst,
                body=original_node.body,
            )
            body_statements: list[Any] = []
            if docstring_statement is not None:
                body_statements.append(docstring_statement)
            body_statements.append(_ellipsis_statement(cst=cst))

            decorators = tuple(
                decorator
                for decorator in updated_node.decorators
                if not _is_signature_neutral_decorator(
                    cst=cst,
                    expression=decorator.decorator,
                    neutral_name_aliases=neutral_name_aliases,
                    neutral_module_aliases=neutral_module_aliases,
                )
            )

            return updated_node.with_changes(
                decorators=decorators,
                body=cst.IndentedBlock(body=tuple(body_statements)),
            )

    return _BaseStubTransformer()


def _collect_signature_neutral_import_aliases(*, module: Any, cst: Any) -> tuple[set[str], dict[str, str]]:
    neutral_name_aliases: set[str] = set()
    neutral_module_aliases: dict[str, str] = {}

    for statement in module.body:
        if not isinstance(statement, cst.SimpleStatementLine):
            continue
        for small_statement in statement.body:
            if isinstance(small_statement, cst.ImportFrom):
                imported_module = _module_name_from_import(cst=cst, module=small_statement.module)
                if imported_module not in _SIGNATURE_NEUTRAL_MODULES:
                    continue
                names = small_statement.names
                if isinstance(names, cst.ImportStar):
                    continue
                for alias in names:
                    local_name = _import_alias_local_name(cst=cst, alias=alias)
                    imported_name = _imported_alias_name(cst=cst, alias=alias)
                    dotted_name = f"{imported_module}.{imported_name}"
                    if dotted_name in _SIGNATURE_NEUTRAL_DECORATOR_WHITELIST:
                        neutral_name_aliases.add(local_name)
            elif isinstance(small_statement, cst.Import):
                for alias in small_statement.names:
                    imported_name = _imported_alias_name(cst=cst, alias=alias)
                    if imported_name in _SIGNATURE_NEUTRAL_MODULES:
                        local_name = _import_alias_local_name(cst=cst, alias=alias)
                        neutral_module_aliases[local_name] = imported_name

    return neutral_name_aliases, neutral_module_aliases


def _module_name_from_import(*, cst: Any, module: Any) -> str | None:
    if module is None:
        return None
    if isinstance(module, cst.Name):
        return module.value
    if isinstance(module, cst.Attribute):
        parts: list[str] = []
        current = module
        while isinstance(current, cst.Attribute):
            parts.append(current.attr.value)
            current = current.value
        if not isinstance(current, cst.Name):
            return None
        parts.append(current.value)
        parts.reverse()
        return ".".join(parts)
    return None


def _import_alias_local_name(*, cst: Any, alias: Any) -> str:
    if alias.asname is not None:
        return alias.asname.name.value

    name = alias.name
    if isinstance(name, cst.Name):
        return name.value
    if isinstance(name, cst.Attribute):
        current = name
        while isinstance(current, cst.Attribute):
            current = current.value
        if isinstance(current, cst.Name):
            return current.value
    msg = "Unsupported import alias structure"
    raise ValueError(msg)


def _imported_alias_name(*, cst: Any, alias: Any) -> str:
    name = alias.name
    if isinstance(name, cst.Name):
        return name.value
    if isinstance(name, cst.Attribute):
        module_name = _module_name_from_import(cst=cst, module=name)
        if module_name is None:
            msg = "Unsupported import alias structure"
            raise ValueError(msg)
        return module_name
    msg = "Unsupported import alias structure"
    raise ValueError(msg)


def _is_signature_neutral_decorator(
    *,
    cst: Any,
    expression: Any,
    neutral_name_aliases: set[str],
    neutral_module_aliases: dict[str, str],
) -> bool:
    if isinstance(expression, cst.Name):
        return expression.value in neutral_name_aliases

    if isinstance(expression, cst.Attribute) and isinstance(expression.value, cst.Name):
        module_name = neutral_module_aliases.get(expression.value.value)
        if module_name is None:
            return False
        dotted_name = f"{module_name}.{expression.attr.value}"
        return dotted_name in _SIGNATURE_NEUTRAL_DECORATOR_WHITELIST

    return False


def _leading_docstring_statement(*, cst: Any, body: Any) -> Any | None:
    if not isinstance(body, cst.IndentedBlock) or not body.body:
        return None
    first_statement = body.body[0]
    if _is_docstring_statement(cst=cst, statement=first_statement):
        return first_statement
    return None


def _is_docstring_statement(*, cst: Any, statement: Any) -> bool:
    if not isinstance(statement, cst.SimpleStatementLine):
        return False
    if len(statement.body) != 1:
        return False
    expression = statement.body[0]
    return isinstance(expression, cst.Expr) and isinstance(expression.value, cst.SimpleString)


def _ellipsis_statement(*, cst: Any) -> Any:
    return cst.SimpleStatementLine(body=(cst.Expr(value=cst.Ellipsis()),))


def _import_libcst() -> Any:
    try:
        return importlib.import_module("libcst")
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Stub generation requested, but 'libcst' is not installed") from exc
