"""Plain decorator example backed by a stub transform."""

from __future__ import annotations

from sigx import stub_transform


@stub_transform("myproj.stub_transforms:add_audit_flag")
def audit[T](func: T) -> T:
    """Wrap a function whose stub includes an ``audit_context`` kwarg."""
    return func
