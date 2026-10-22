"""FastAPI 应用入口。

启动方式（在 backend 目录下）::

    python -m uvicorn app.main:app --port 8000

然后浏览器访问 http://localhost:8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import get_settings
from app.db.base import init_db
from app.db.seed import seed_if_empty
from app.services.llm.factory import is_demo_mode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cyber-girlfriend")

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
STATIC_DIR = BASE_DIR / "static"

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("数据库就绪：%s", settings.database_url)
    created = seed_if_empty()
    if created:
        logger.info("已写入 %d 个示例人格（角色墙不为空）", created)
    if is_demo_mode():
        logger.info("当前为演示模式（mock provider），无需任何 API Key 即可体验")
    yield
    logger.info("服务已停止")


app = FastAPI(
    title="Cyber Girlfriend API",
    description="赛博女友 —— 本地优先的 AI 聊天搭子（demo）",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/api/meta")
def api_meta() -> JSONResponse:
    """前端启动时读取的基础元信息。"""
    cfg = {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
    }
    return JSONResponse(
        {
            "name": "cyber-girlfriend",
            "version": app.version,
            "demo_mode": is_demo_mode(cfg),
            "providers": ["mock", "openai", "ollama"],
            "features": [
                "聊天记录导入",
                "人设自动提取",
                "长期记忆与检索",
                "流式打字机回复",
                "点赞/踩/改写反馈",
                "酒馆角色卡导入导出",
                "世界书（Lorebook）注入",
                "导入隐私脱敏",
                "全量备份导出导入",
            ],
            "api_version": "0.2.0",
        }
    )


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")


# 静态资源（app.js / style.css / vendor/vue.global.prod.js）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="site")


__all__ = ["app"]
