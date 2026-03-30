from __future__ import annotations

from myproj.decorators import add_kwargs


@add_kwargs(["debug", "trace"])
def run_job(name: str) -> None:
    pass


class Worker:
    @add_kwargs(["attempt"])
    def process(self, name: str) -> None:
        pass
