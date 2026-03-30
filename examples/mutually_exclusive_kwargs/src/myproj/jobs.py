from __future__ import annotations

from myproj.decorators import either_a_or_b


@either_a_or_b
def run_job(name: str) -> None:
    pass
