"""Example tasks that use the plain audit decorator."""

from __future__ import annotations

from myproj.decorators import audit


@audit
def save_task(task_id: int) -> bool:
    """Persist a task and report success."""
    _ = task_id
    return True
