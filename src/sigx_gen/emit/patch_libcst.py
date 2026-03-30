"""LibCST-powered patch backend for applying transform plans."""

from __future__ import annotations

from collections import defaultdict
import importlib
from typing import Any

from sigx_gen.emit.patch_base import StubPatchBackend
from sigx_gen.model.diagnostics import Diagnostic, DiagnosticLevel
from sigx_gen.model.plan import ModulePlan, SymbolPlan


def build_libcst_backend() -> StubPatchBackend:
    """Build a LibCST patch backend.

    Returns:
        Configured patch backend instance.

    Raises:
        RuntimeError: If LibCST is not installed.
    """
    try:
        cst = importlib.import_module("libcst")
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("LibCST backend requested, but 'libcst' is not installed") from exc
    return _LibCSTPatchBackend(cst)


class _LibCSTPatchBackend:
    """Patch backend implementation using LibCST transformations."""

    def __init__(self, cst: Any) -> None:
        """Initialize backend.

        Args:
            cst: Imported ``libcst`` module object.
        """
        self._cst = cst

    def patch_module(self, existing_text: str, module_plan: ModulePlan) -> tuple[str, tuple[Diagnostic, ...]]:
        """Patch one module stub text.

        Args:
            existing_text: Current module stub text.
            module_plan: Module patch plan.

        Returns:
            Patched text and diagnostics.
        """
        cst = self._cst
        module = cst.parse_module(existing_text)
        targets_top: dict[str, SymbolPlan] = {}
        targets_by_class: dict[str, dict[str, SymbolPlan]] = defaultdict(dict)
        for symbol in module_plan.symbols:
            if symbol.class_name is None:
                targets_top[symbol.function_name] = symbol
            else:
                targets_by_class[symbol.class_name][symbol.function_name] = symbol

        import_lines = [
            *(f"import {name}" for name in module_plan.module_imports),
            *([f"from typing import {', '.join(module_plan.typing_imports)}"] if module_plan.typing_imports else []),
        ]
        missing_import_lines = [line for line in import_lines if line not in existing_text]

        diagnostics: list[Diagnostic] = []
        seen_classes: set[str] = set()

        backend = self

        class _Patcher(cst.CSTTransformer):  # type: ignore[misc]
            def leave_ClassDef(self, original_node: Any, updated_node: Any) -> Any:
                seen_classes.add(updated_node.name.value)
                class_targets = targets_by_class.get(updated_node.name.value)
                if not class_targets:
                    return updated_node

                replaced_body, replaced_names = backend._replace_scope_body(
                    statements=list(updated_node.body.body),
                    targets=class_targets,
                )
                for method_name, symbol in class_targets.items():
                    if method_name in replaced_names:
                        continue
                    diagnostics.append(
                        Diagnostic(
                            level=DiagnosticLevel.WARNING,
                            code="SX021",
                            message=f"Method not found in stub; appending overloads: {symbol.qualname}",
                            module_name=module_plan.module_name,
                            qualname=symbol.qualname,
                            file_path=str(module_plan.stub_file),
                        )
                    )
                    replaced_body.extend(backend._symbol_statements(symbol))

                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=tuple(replaced_body)),
                )

            def leave_Module(self, original_node: Any, updated_node: Any) -> Any:
                replaced_body, replaced_names = backend._replace_scope_body(
                    statements=list(updated_node.body),
                    targets=targets_top,
                )
                for function_name, symbol in targets_top.items():
                    if function_name in replaced_names:
                        continue
                    diagnostics.append(
                        Diagnostic(
                            level=DiagnosticLevel.WARNING,
                            code="SX021",
                            message=f"Function not found in stub; appending overloads: {symbol.qualname}",
                            module_name=module_plan.module_name,
                            qualname=symbol.qualname,
                            file_path=str(module_plan.stub_file),
                        )
                    )
                    replaced_body.extend(backend._symbol_statements(symbol))

                missing_classes = sorted(set(targets_by_class) - seen_classes)
                for class_name in missing_classes:
                    diagnostics.append(
                        Diagnostic(
                            level=DiagnosticLevel.ERROR,
                            code="SX021",
                            message=f"Class not found in stub for method patching: {class_name}",
                            module_name=module_plan.module_name,
                            file_path=str(module_plan.stub_file),
                        )
                    )

                if missing_import_lines:
                    insertion_index = backend._import_insertion_index(replaced_body)
                    import_statements = backend._parse_statements("\n".join(missing_import_lines))
                    replaced_body[insertion_index:insertion_index] = import_statements

                return updated_node.with_changes(body=tuple(replaced_body))

        patched_module = module.visit(_Patcher())
        return patched_module.code, tuple(diagnostics)

    def _replace_scope_body(
        self,
        *,
        statements: list[Any],
        targets: dict[str, SymbolPlan],
    ) -> tuple[list[Any], set[str]]:
        cst = self._cst
        replaced_names: set[str] = set()
        new_body: list[Any] = []
        index = 0
        while index < len(statements):
            statement = statements[index]
            if isinstance(statement, cst.FunctionDef):
                function_name = statement.name.value
                symbol = targets.get(function_name)
                if symbol is not None and function_name not in replaced_names:
                    replaced_names.add(function_name)
                    new_body.extend(self._symbol_statements(symbol))
                    index += 1
                    while index < len(statements):
                        next_statement = statements[index]
                        if isinstance(next_statement, cst.FunctionDef) and next_statement.name.value == function_name:
                            index += 1
                            continue
                        break
                    continue

            new_body.append(statement)
            index += 1

        return new_body, replaced_names

    def _symbol_statements(self, symbol: SymbolPlan) -> list[Any]:
        if len(symbol.rendered_signatures) == 1:
            text = f"def {symbol.function_name}{symbol.rendered_signatures[0]}: ..."
            return self._parse_statements(text)

        lines: list[str] = []
        for signature in symbol.rendered_signatures:
            lines.append("@overload")
            lines.append(f"def {symbol.function_name}{signature}: ...")
        return self._parse_statements("\n".join(lines))

    def _parse_statements(self, text: str) -> list[Any]:
        module = self._cst.parse_module(text + "\n")
        return list(module.body)

    def _import_insertion_index(self, statements: list[Any]) -> int:
        cst = self._cst
        index = 0
        if statements and self._is_docstring_statement(statements[0]):
            index = 1
        while index < len(statements):
            statement = statements[index]
            if self._is_future_import(statement):
                index += 1
                continue
            break
        return index

    def _is_docstring_statement(self, statement: Any) -> bool:
        cst = self._cst
        if not isinstance(statement, cst.SimpleStatementLine):
            return False
        if len(statement.body) != 1:
            return False
        expr = statement.body[0]
        return isinstance(expr, cst.Expr) and isinstance(expr.value, cst.SimpleString)

    def _is_future_import(self, statement: Any) -> bool:
        cst = self._cst
        if not isinstance(statement, cst.SimpleStatementLine):
            return False
        if len(statement.body) != 1:
            return False
        import_from = statement.body[0]
        if not isinstance(import_from, cst.ImportFrom):
            return False
        module = import_from.module
        if isinstance(module, cst.Name):
            return module.value == "__future__"
        return False
