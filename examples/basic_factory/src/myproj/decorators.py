"""Decorator factory example for adding keyword-only stub arguments."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sigx import stub_transform_factory

F = TypeVar("F")


@stub_transform_factory("myproj.stub_transforms:add_kwargs_transform")
def add_kwargs(kwarg_list: list[str]) -> Callable[[F], F]:
    """Return a decorator that adds the configured keyword-only arguments."""
    _ = kwarg_list

    def decorator(func: F) -> F:
        return func

    return decorator
