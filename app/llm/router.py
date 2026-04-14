# app/llm/router.py
# BSL 1.1 License
"""
Snipe LLMRouter shim — tri-level config path priority.

Config lookup order:
  1. <repo>/config/llm.yaml  — per-install local override
  2. ~/.config/circuitforge/llm.yaml  — user-level config (circuitforge-core default)
  3. env-var auto-config  (ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_HOST, CF_ORCH_URL)
"""
from pathlib import Path

from circuitforge_core.llm import LLMRouter as _CoreLLMRouter

_REPO_CONFIG = Path(__file__).parent.parent.parent / "config" / "llm.yaml"
_USER_CONFIG = Path.home() / ".config" / "circuitforge" / "llm.yaml"


class LLMRouter(_CoreLLMRouter):
    """Snipe-specific LLMRouter with tri-level config resolution.

    Explicit ``config_path`` bypasses the lookup (useful in tests).
    """

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is not None:
            super().__init__(config_path)
            return

        if _REPO_CONFIG.exists():
            super().__init__(_REPO_CONFIG)
        elif _USER_CONFIG.exists():
            super().__init__(_USER_CONFIG)
        else:
            # No yaml — let circuitforge-core env-var auto-config handle it.
            super().__init__()
