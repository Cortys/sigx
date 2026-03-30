from __future__ import annotations

from myproj.decorators import add_kwargs

MAX_RETRIES: int = 3


class Payload:
    pass


@add_kwargs(["debug", "trace"])
def run_job(name: str) -> None:
    pass


def helper(payload: Payload) -> int:
    return MAX_RETRIES


class Worker:
    @add_kwargs(["attempt"])
    def process(self, name: str) -> None:
        pass

    def ping(self, payload: Payload) -> int:
        return MAX_RETRIES
