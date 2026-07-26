from __future__ import annotations

import hashlib
import re
from pathlib import Path

PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"忽略.{0,8}(之前|以上|系统).{0,8}(指令|规则)"),
    re.compile(r"system\s*prompt", re.IGNORECASE),
)


def redact_text(value: str, limit: int = 280) -> str:
    """Create a stable, bounded trace summary without logging full user content."""
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{compact[:limit]}… [sha256:{digest}]"


def contains_prompt_injection(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in PROMPT_INJECTION_PATTERNS)


def safe_workspace_path(root: Path, *parts: str) -> Path:
    """Resolve a workspace path and reject absolute paths or traversal."""
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError("Path escapes the configured workspace root")
    return candidate

