from __future__ import annotations

from sigx_gen.model.diagnostics import Diagnostic, DiagnosticLevel


def test_diagnostic_model_fields() -> None:
    diagnostic = Diagnostic(level=DiagnosticLevel.WARNING, code="SX001", message="msg", module_name="pkg.mod")

    assert diagnostic.level is DiagnosticLevel.WARNING
    assert diagnostic.code == "SX001"
    assert diagnostic.module_name == "pkg.mod"
