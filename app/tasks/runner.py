# app/tasks/runner.py
"""Snipe background task runner.

Implements the run_task_fn interface expected by circuitforge_core.tasks.scheduler.

Current task types:
    trust_photo_analysis — download primary photo, run vision LLM, write
                           result to trust_scores.photo_analysis_json (Paid tier).

Image assessment routing:
    Cloud (GPU_SERVER_URL set): allocates via cf-orch task endpoint
        product=snipe, task=image_assessment.
    Local (no GPU_SERVER_URL) or TaskNotFound fallback: uses LLMRouter
        with a vision-capable local backend (moondream2, llava, etc.).
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

import httpx
import requests
from circuitforge_core.db import get_connection

log = logging.getLogger(__name__)

LLM_TASK_TYPES: frozenset[str] = frozenset({"trust_photo_analysis"})

VRAM_BUDGETS: dict[str, float] = {
    "trust_photo_analysis": 6000,  # Q5_K_M Qwen2-VL via cf-orch; LLMRouter fallback uses 2.0 GB
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
    """Insert a background task if no identical task is already in-flight.

    Returns (task_id, is_new).
    """
    conn = get_connection(db_path)
    conn.row_factory = __import__("sqlite3").Row
    try:
        existing = conn.execute(
            "SELECT id FROM background_tasks "
            "WHERE task_type=? AND job_id=? AND status IN ('queued','running')",
            (task_type, job_id),
        ).fetchone()
        if existing:
            return existing["id"], False
        cursor = conn.execute(
            "INSERT INTO background_tasks (task_type, job_id, params) VALUES (?,?,?)",
            (task_type, job_id, params),
        )
        conn.commit()
        return cursor.lastrowid, True
    finally:
        conn.close()


def _update_task_status(
    db_path: Path, task_id: int, status: str, *, error: str = ""
) -> None:
    with get_connection(db_path) as conn:
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
    """Download primary listing photo, run vision LLM, write to trust_scores.

    In cloud mode the result must be written to the per-user DB, which differs
    from db_path (the scheduler's shared task-queue DB).  The enqueue call site
    encodes the correct write target as 'user_db' in params; in local mode it
    falls back to db_path so the single-DB layout keeps working.
    """
    p = json.loads(params or "{}")
    photo_url = p.get("photo_url", "")
    listing_title = p.get("listing_title", "")
    result_db = Path(p.get("user_db", str(db_path)))

    if not photo_url:
        raise ValueError("trust_photo_analysis: 'photo_url' is required in params")

    resp = requests.get(photo_url, timeout=10)
    resp.raise_for_status()
    image_b64 = base64.b64encode(resp.content).decode()
    image_data_url = f"data:image/jpeg;base64,{image_b64}"

    user_prompt = "Assess this listing image."
    if listing_title:
        user_prompt = f"Assess this eBay listing image: {listing_title}"

    cforch_url = os.getenv("GPU_SERVER_URL") or os.getenv("CF_ORCH_URL")
    if cforch_url:
        raw = _assess_via_orch(cforch_url, image_data_url, user_prompt)
    else:
        raw = _assess_via_local_llm(image_b64, user_prompt)

    try:
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        analysis = json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning(
            "Vision LLM returned non-JSON for listing %d: %r", listing_id, raw[:200]
        )
        analysis = {"raw_response": raw, "parse_error": True}

    with get_connection(result_db) as conn:
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


def _assess_via_orch(cforch_url: str, image_data_url: str, user_prompt: str) -> str:
    """Run photo assessment via cf-orch task endpoint (cloud path)."""
    from circuitforge_orch.client import CFOrchClient, TaskNotFound

    client = CFOrchClient(cforch_url)
    try:
        with client.task_allocate("snipe", "image_assessment") as alloc:
            resp = httpx.post(
                f"{alloc.url}/v1/chat/completions",
                json={
                    "model": alloc.model or "__auto__",
                    "messages": [
                        {
                            "role": "system",
                            "content": _VISION_SYSTEM_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": image_data_url}},
                                {"type": "text", "text": user_prompt},
                            ],
                        },
                    ],
                    "max_tokens": 128,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except TaskNotFound:
        log.warning(
            "snipe.image_assessment not registered in cf-orch — falling back to local LLM"
        )
        image_b64 = image_data_url.split(",", 1)[1]
        return _assess_via_local_llm(image_b64, user_prompt)


def _assess_via_local_llm(image_b64: str, user_prompt: str) -> str:
    """Run photo assessment via local LLMRouter (local/self-hosted path)."""
    from app.llm.router import LLMRouter

    router = LLMRouter()
    return router.complete(
        user_prompt,
        system=_VISION_SYSTEM_PROMPT,
        images=[image_b64],
        max_tokens=128,
    )
