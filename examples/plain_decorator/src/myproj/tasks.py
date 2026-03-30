from __future__ import annotations

from myproj.decorators import audit


@audit
def save_task(task_id: int) -> bool:
    return True
