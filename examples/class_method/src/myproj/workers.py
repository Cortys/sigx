from __future__ import annotations

from myproj.decorators import add_kwargs


class Worker:
    @add_kwargs(["attempt", "trace_id"])
    def process(self, payload: str) -> None:
        pass
