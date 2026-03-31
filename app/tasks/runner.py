# app/tasks/runner.py
"""Snipe background task runner.

Implements the run_task_fn interface expected by circuitforge_core.tasks.scheduler.

Current task types:
    trust_photo_analysis — download primary photo, run vision LLM, write
                           result to trust_scores.photo_analysis_json (Paid tier).

Prompt note: The vision prompt is a functional first pass. Tune against real
eBay listings before GA — specifically stock-photo vs genuine-product distinction
and the damage vocabulary.
"""
from __future__ import annotations

import base64
import json
import logging
import sqlite3
from pathlib import Path

import requests

from circuitforge_core.llm import LLMRouter

log = logging.getLogger(__name__)

LLM_TASK_TYPES: frozenset[str] = frozenset({"trust_photo_analysis"})

VRAM_BUDGETS: dict[str, float] = {
    # moondream2 / vision-capable LLM — single image, short response
    "trust_photo_analysis": 2.0,
}

_VISION_SYSTEM_PROMPT = (
    "You are an expert at evaluating eBay listing photos for authenticity and condition. "
    "Respond ONLY with a JSON object containing these exact keys:\n"
    "  is_stock_photo: bool — true if this looks like a manufacturer/marketing image\n"
    "  visible_damage: bool — true if scratches, dents, cracks, or defects are visible\n"
    "  authenticity_signal: string — one of 'genuine_product_photo', 'stock_photo', 'unclear'\n"
    "  confidence: string — one of 'high', 'medium', 'low'\n"
    "No explanation outside the JSON object."
)


def insert_task(
    db_path: Path,
    task_type: str,
    job_id: int,
    *,
    params: str | None = None,
) -> tuple[int, bool]:
    """Insert a background task if no identical task is already in-flight."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    existing = conn.execute(
        "SELECT id FROM background_tasks "
        "WHERE task_type=? AND job_id=? AND status IN ('queued','running')",
        (task_type, job_id),
    ).fetchone()
    if existing:
        conn.close()
        return existing["id"], False
    cursor = conn.execute(
        "INSERT INTO background_tasks (task_type, job_id, params) VALUES (?,?,?)",
        (task_type, job_id, params),
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id, True


def _update_task_status(
    db_path: Path, task_id: int, status: str, *, error: str = ""
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE background_tasks "
            "SET status=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, error, task_id),
        )


def run_task(
    db_path: Path,
    task_id: int,
    task_type: str,
    job_id: int,
    params: str | None = None,
) -> None:
    """Execute one background task. Called by the scheduler's batch worker."""
    _update_task_status(db_path, task_id, "running")
    try:
        if task_type == "trust_photo_analysis":
            _run_trust_photo_analysis(db_path, job_id, params)
        else:
            raise ValueError(f"Unknown snipe task type: {task_type!r}")
        _update_task_status(db_path, task_id, "completed")
    except Exception as exc:
        log.exception("Task %d (%s) failed: %s", task_id, task_type, exc)
        _update_task_status(db_path, task_id, "failed", error=str(exc))


def _run_trust_photo_analysis(
    db_path: Path,
    listing_id: int,
    params: str | None,
) -> None:
    """Download primary listing photo, run vision LLM, write to trust_scores."""
    p = json.loads(params or "{}")
    photo_url = p.get("photo_url", "")
    listing_title = p.get("listing_title", "")

    if not photo_url:
        raise ValueError("trust_photo_analysis: 'photo_url' is required in params")

    # Download and base64-encode the photo
    resp = requests.get(photo_url, timeout=10)
    resp.raise_for_status()
    image_b64 = base64.b64encode(resp.content).decode()

    # Build user prompt with optional title context
    user_prompt = "Evaluate this eBay listing photo."
    if listing_title:
        user_prompt = f"Evaluate this eBay listing photo for: {listing_title}"

    # Call LLMRouter with vision capability
    router = LLMRouter()
    raw = router.complete(
        user_prompt,
        system=_VISION_SYSTEM_PROMPT,
        images=[image_b64],
        max_tokens=128,
    )

    # Parse — be lenient: strip markdown fences if present
    try:
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        analysis = json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning(
            "Vision LLM returned non-JSON for listing %d: %r", listing_id, raw[:200]
        )
        analysis = {"raw_response": raw, "parse_error": True}

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE trust_scores SET photo_analysis_json=? WHERE listing_id=?",
            (json.dumps(analysis), listing_id),
        )

    log.info(
        "Vision analysis for listing %d: stock=%s damage=%s confidence=%s",
        listing_id,
        analysis.get("is_stock_photo"),
        analysis.get("visible_damage"),
        analysis.get("confidence"),
    )
