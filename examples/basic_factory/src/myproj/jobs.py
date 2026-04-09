"""Example jobs that use the factory-based decorator."""

from __future__ import annotations

from myproj.decorators import add_kwargs


@add_kwargs(["debug", "trace"])
def run_job(name: str) -> None:
    """Run a job with additional generated keyword-only options."""
