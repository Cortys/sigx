"""Decorator example for mutually exclusive keyword-only additions."""

from __future__ import annotations

from sigx import stub_transform


@stub_transform("myproj.stub_transforms:either_a_or_b")
def either_a_or_b[T](func: T) -> T:
    """Wrap a function that supports either of two kw-only options."""
    return func
