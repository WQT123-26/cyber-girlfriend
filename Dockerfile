# syntax=docker/dockerfile:1
#
# 赛博女友 / cyber-girlfriend —— 生产可用镜像（单阶段，依赖全部为纯 Python 包）
#
# 构建：
#   docker build -t cyber-girlfriend:0.2.0 .
# 运行：
#   docker run -p 8000:8000 -v "%cd%\backend\data:/app/data" cyber-girlfriend:0.2.0
#
# 说明：
#   * 默认使用 mock provider，构建与启动都**不需要任何 API Key**。
#   * 数据目录固定为 /app/data（已声明 VOLUME），SQLite 文件为 /app/data/cyber_gf.db。

FROM python:3.11-slim

LABEL org.opencontainers.image.title="cyber-girlfriend" \
      org.opencontainers.image.description="本地优先的 AI 聊天搭子（FastAPI + SQLite + 零构建 Vue 3）" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="0.2.0"

# 不写 pyc、日志实时刷新；数据库落在挂载卷内
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CG_DATABASE_URL=sqlite:////app/data/cyber_gf.db

WORKDIR /app

# 先装依赖，利用层缓存：仅 requirements.txt 变化时才重新 pip install
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 再拷业务代码（前端静态资源一并带入，无需 Node 构建）
COPY backend/ /app/

# 数据目录（SQLite）与卷声明
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

# 健康检查：slim 镜像无 curl，用标准库 urllib 探测 /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

# 注意：默认以 root 运行，以便绑定挂载（./backend/data）在任意宿主机上都可写。
# 如需加固，可自行创建非 root 用户并确保挂载目录对其可写。
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
