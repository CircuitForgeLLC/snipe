"""GPU architecture and VRAM scoring for laptop mainboard inference-value ranking.

Parses GPU model names from eBay listing titles and scores them on two axes:
  - vram_score:  linear 0–100, anchored at 24 GB = 100
  - arch_score:  linear 0–100, architecture tier 1–5 (5 = newest)

inference_score = (vram_score × vram_weight + arch_score × arch_weight)
                  / (vram_weight + arch_weight)

Patterns are matched longest-first to prevent "RTX 3070" matching before "RTX 3070 Ti".
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuSpec:
    model: str        # canonical name, e.g. "RTX 3070 Ti"
    vram_gb: int
    arch_tier: int    # 1–5; 5 = newest generation
    arch_name: str    # human-readable, e.g. "Ampere"
    vendor: str       # "nvidia" | "amd" | "intel"


@dataclass
class GpuMatch:
    spec: GpuSpec
    vram_score: float
    arch_score: float
    inference_score: float


# ── GPU database ──────────────────────────────────────────────────────────────
# Laptop VRAM often differs from desktop; using common laptop variants.
# Listed longest-name-first within each family to guide sort order.

_GPU_DB: list[GpuSpec] = [
    # NVIDIA Ada Lovelace — tier 5
    GpuSpec("RTX 4090", 16, 5, "Ada Lovelace", "nvidia"),
    GpuSpec("RTX 4080", 12, 5, "Ada Lovelace", "nvidia"),
    GpuSpec("RTX 4070 Ti", 12, 5, "Ada Lovelace", "nvidia"),
    GpuSpec("RTX 4070", 8, 5, "Ada Lovelace", "nvidia"),
    GpuSpec("RTX 4060 Ti", 8, 5, "Ada Lovelace", "nvidia"),
    GpuSpec("RTX 4060", 8, 5, "Ada Lovelace", "nvidia"),
    GpuSpec("RTX 4050", 6, 5, "Ada Lovelace", "nvidia"),
    # NVIDIA Ampere — tier 4
    GpuSpec("RTX 3090", 24, 4, "Ampere", "nvidia"),   # rare laptop variant
    GpuSpec("RTX 3080 Ti", 16, 4, "Ampere", "nvidia"),
    GpuSpec("RTX 3080", 8, 4, "Ampere", "nvidia"),    # most laptop 3080s = 8 GB
    GpuSpec("RTX 3070 Ti", 8, 4, "Ampere", "nvidia"),
    GpuSpec("RTX 3070", 8, 4, "Ampere", "nvidia"),
    GpuSpec("RTX 3060", 6, 4, "Ampere", "nvidia"),
    GpuSpec("RTX 3050 Ti", 4, 4, "Ampere", "nvidia"),
    GpuSpec("RTX 3050", 4, 4, "Ampere", "nvidia"),
    # NVIDIA Turing — tier 3
    GpuSpec("RTX 2080", 8, 3, "Turing", "nvidia"),
    GpuSpec("RTX 2070", 8, 3, "Turing", "nvidia"),
    GpuSpec("RTX 2060", 6, 3, "Turing", "nvidia"),
    GpuSpec("GTX 1660 Ti", 6, 3, "Turing", "nvidia"),
    GpuSpec("GTX 1660", 6, 3, "Turing", "nvidia"),
    GpuSpec("GTX 1650 Ti", 4, 3, "Turing", "nvidia"),
    GpuSpec("GTX 1650", 4, 3, "Turing", "nvidia"),
    # NVIDIA Pascal — tier 2
    GpuSpec("GTX 1080", 8, 2, "Pascal", "nvidia"),
    GpuSpec("GTX 1070", 8, 2, "Pascal", "nvidia"),
    GpuSpec("GTX 1060", 6, 2, "Pascal", "nvidia"),
    GpuSpec("GTX 1050 Ti", 4, 2, "Pascal", "nvidia"),
    GpuSpec("GTX 1050", 4, 2, "Pascal", "nvidia"),
    # AMD RDNA3 — tier 5
    GpuSpec("RX 7900M", 16, 5, "RDNA3", "amd"),
    GpuSpec("RX 7700S", 8, 5, "RDNA3", "amd"),
    GpuSpec("RX 7600M XT", 8, 5, "RDNA3", "amd"),
    GpuSpec("RX 7600S", 8, 5, "RDNA3", "amd"),
    GpuSpec("RX 7600M", 8, 5, "RDNA3", "amd"),
    # AMD RDNA2 — tier 4
    GpuSpec("RX 6850M XT", 12, 4, "RDNA2", "amd"),
    GpuSpec("RX 6800S", 12, 4, "RDNA2", "amd"),
    GpuSpec("RX 6800M", 12, 4, "RDNA2", "amd"),
    GpuSpec("RX 6700S", 10, 4, "RDNA2", "amd"),
    GpuSpec("RX 6700M", 10, 4, "RDNA2", "amd"),
    GpuSpec("RX 6650M", 8, 4, "RDNA2", "amd"),
    GpuSpec("RX 6600S", 8, 4, "RDNA2", "amd"),
    GpuSpec("RX 6600M", 8, 4, "RDNA2", "amd"),
    GpuSpec("RX 6500M", 4, 4, "RDNA2", "amd"),
    # AMD RDNA1 — tier 3
    GpuSpec("RX 5700M", 8, 3, "RDNA1", "amd"),
    GpuSpec("RX 5600M", 6, 3, "RDNA1", "amd"),
    GpuSpec("RX 5500M", 4, 3, "RDNA1", "amd"),
    # Intel Arc Alchemist — tier 4 (improving ROCm/IPEX-LLM support)
    GpuSpec("Arc A770M", 16, 4, "Alchemist", "intel"),
    GpuSpec("Arc A550M", 8, 4, "Alchemist", "intel"),
    GpuSpec("Arc A370M", 4, 4, "Alchemist", "intel"),
    GpuSpec("Arc A350M", 4, 4, "Alchemist", "intel"),
]


def _build_patterns() -> list[tuple[re.Pattern[str], GpuSpec]]:
    """Compile regex patterns, sorted longest-model-name first to prevent prefix shadowing."""
    result = []
    for spec in sorted(_GPU_DB, key=lambda s: -len(s.model)):
        # Allow optional space or hyphen between tokens (e.g. "RTX3070" or "RTX-3070")
        escaped = re.escape(spec.model).replace(r"\ ", r"[\s\-]?")
        result.append((re.compile(escaped, re.IGNORECASE), spec))
    return result


_PATTERNS: list[tuple[re.Pattern[str], GpuSpec]] = _build_patterns()


def parse_gpu(title: str) -> GpuSpec | None:
    """Return the first GPU model found in a listing title, or None."""
    for pattern, spec in _PATTERNS:
        if pattern.search(title):
            return spec
    return None


def score_gpu(spec: GpuSpec, vram_weight: float, arch_weight: float) -> GpuMatch:
    """Compute normalized inference value scores for a GPU spec.

    vram_score: linear scale, 24 GB anchors at 100. Capped at 100.
    arch_score: linear scale, tier 1 = 0, tier 5 = 100.
    inference_score: weighted average of both, normalized to the total weight.
    """
    vram_score = min(100.0, (spec.vram_gb / 24.0) * 100.0)
    arch_score = ((spec.arch_tier - 1) / 4.0) * 100.0

    total_weight = vram_weight + arch_weight
    if total_weight <= 0:
        inference_score = 0.0
    else:
        inference_score = (
            vram_score * vram_weight + arch_score * arch_weight
        ) / total_weight

    return GpuMatch(
        spec=spec,
        vram_score=round(vram_score, 1),
        arch_score=round(arch_score, 1),
        inference_score=round(inference_score, 1),
    )
