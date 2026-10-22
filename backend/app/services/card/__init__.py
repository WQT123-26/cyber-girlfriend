"""角色卡（SillyTavern Character Card）服务包。

对外统一导出：解析 / 生成 / 字段映射，纯标准库实现，零新依赖。
"""

from app.services.card.st_card import (
    CARD_FIELDS,
    CardParseError,
    V2_SPEC,
    V3_SPEC,
    build_card_png,
    build_mes_example,
    card_to_persona,
    card_to_worldbook_entries,
    embed_card_json_to_png,
    extract_card_json_from_png,
    make_gradient_png,
    normalize_card,
    parse_card_payload,
    persona_to_card,
    read_png_text_chunks,
    split_mes_example,
    worldbook_entries_to_character_book,
)

__all__ = [
    "CARD_FIELDS",
    "CardParseError",
    "V2_SPEC",
    "V3_SPEC",
    "build_card_png",
    "build_mes_example",
    "card_to_persona",
    "card_to_worldbook_entries",
    "embed_card_json_to_png",
    "extract_card_json_from_png",
    "make_gradient_png",
    "normalize_card",
    "parse_card_payload",
    "persona_to_card",
    "read_png_text_chunks",
    "split_mes_example",
    "worldbook_entries_to_character_book",
]
