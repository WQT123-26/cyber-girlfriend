"""世界书 / Lorebook 子包。

* ``matcher`` —— 关键词匹配、预算裁剪、按位置注入 prompt
"""

from app.services.lore.matcher import (  # noqa: F401
    BLOCK_TITLE,
    DEFAULT_DEPTH,
    DEFAULT_SCAN_ROUNDS,
    VALID_POSITIONS,
    LoreHit,
    build_scan_text,
    collect_hits,
    estimate_tokens,
    inject_into_messages,
    injection_summary,
    load_entries,
    match_entries,
    normalize_position,
    render_block,
    split_by_position,
)

__all__ = [
    "BLOCK_TITLE",
    "DEFAULT_DEPTH",
    "DEFAULT_SCAN_ROUNDS",
    "LoreHit",
    "VALID_POSITIONS",
    "build_scan_text",
    "collect_hits",
    "estimate_tokens",
    "inject_into_messages",
    "injection_summary",
    "load_entries",
    "match_entries",
    "normalize_position",
    "render_block",
    "split_by_position",
]
