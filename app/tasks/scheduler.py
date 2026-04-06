# app/tasks/scheduler.py
"""Snipe LLM/vision task scheduler — thin shim over circuitforge_core.tasks.scheduler."""
from __future__ import annotations

from pathlib import Path

from circuitforge_core.tasks.scheduler import (
    TaskScheduler,  # re-export for tests
)
from circuitforge_core.tasks.scheduler import (
    get_scheduler as _base_get_scheduler,
)

from app.tasks.runner import LLM_TASK_TYPES, VRAM_BUDGETS, run_task


def get_scheduler(db_path: Path) -> TaskScheduler:
    """Return the process-level TaskScheduler singleton for Snipe."""
    return _base_get_scheduler(
        db_path=db_path,
        run_task_fn=run_task,
        task_types=LLM_TASK_TYPES,
        vram_budgets=VRAM_BUDGETS,
    )
