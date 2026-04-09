"""Example worker class that uses decorated methods."""

from __future__ import annotations

from myproj.decorators import add_kwargs


class Worker:
    """Process units of work with decorated method signatures."""

    @add_kwargs(["attempt", "trace_id"])
    def process(self, payload: str) -> None:
        """Process a single payload."""
