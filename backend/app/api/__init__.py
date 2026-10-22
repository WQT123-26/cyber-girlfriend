"""API 路由聚合。

本次迭代新增：
    ``cards``    —— SillyTavern 角色卡导入 / 解析 / 导出
    ``worldbook``—— 世界书（Lorebook）CRUD 与命中预览
    ``backup``   —— 全量备份导出 / 合并导入
"""

from fastapi import APIRouter

from app.api import (
    backup,
    cards,
    chat,
    feedback,
    importer,
    memory,
    personas,
    sessions_api,
    settings_api,
    worldbook,
)

api_router = APIRouter()
api_router.include_router(personas.router)
api_router.include_router(cards.router)
api_router.include_router(worldbook.router)
api_router.include_router(importer.router)
api_router.include_router(sessions_api.router)
api_router.include_router(chat.router)
api_router.include_router(memory.router)
api_router.include_router(settings_api.router)
api_router.include_router(feedback.router)
api_router.include_router(backup.router)

__all__ = ["api_router"]
