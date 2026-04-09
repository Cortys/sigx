"""Example pipeline using stacked decorator factories."""

from __future__ import annotations

from myproj.decorators import add_kwargs


@add_kwargs(["trace_id"])
@add_kwargs(["debug"])
def execute(name: str, *args: object, **kwargs: object) -> None:
    """Execute a pipeline step with additional generated keyword options."""
