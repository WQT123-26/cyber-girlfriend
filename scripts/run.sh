#!/usr/bin/env bash
# ==========================================================================
#  赛博女友 CyberGirlfriend - 一键安装依赖并启动（Linux / macOS）
#  用法： bash scripts/run.sh   或   ./scripts/run.sh
# ==========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"
PORT="${CG_PORT:-8000}"

echo
echo "=========================================================="
echo "  赛博女友 CyberGirlfriend - 启动脚本"
echo "=========================================================="
echo

if [ ! -f "$BACKEND_DIR/app/main.py" ]; then
  echo "[错误] 未找到后端目录：$BACKEND_DIR"
  echo "       请确认本脚本位于项目的 scripts/ 目录下。"
  exit 1
fi

cd "$BACKEND_DIR"

# ---------- 1. 检查 Python ----------
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "[错误] 未检测到 python3，请先安装 Python 3.10+。"
  exit 1
fi
echo "[1/4] Python：$("$PYTHON" -c 'import sys;print(sys.version.split()[0])')"

# ---------- 2. 创建 / 激活虚拟环境 ----------
if [ ! -x ".venv/bin/python" ]; then
  echo "[2/4] 创建虚拟环境 .venv ..."
  "$PYTHON" -m venv .venv
else
  echo "[2/4] 复用已有虚拟环境 .venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
PY=".venv/bin/python"

# ---------- 3. 安装依赖 ----------
echo "[3/4] 安装依赖（首次较慢，请耐心等待）..."
"$PY" -m pip install --upgrade pip --quiet
if ! "$PY" -m pip install -r requirements.txt; then
  echo
  echo "[错误] 依赖安装失败，请检查网络或 pip 配置。"
  echo "       可手动执行： $PY -m pip install -r requirements.txt"
  exit 1
fi

# ---------- 4. 启动服务 ----------
echo "[4/4] 启动服务： http://localhost:${PORT}"
echo
echo "  访问地址： http://localhost:${PORT}"
echo "  接口文档： http://localhost:${PORT}/docs"
echo "  停止服务： Ctrl + C"
echo
echo "  当前默认使用 mock 演示模型，无需任何 API Key。"
echo "  若需真实模型，请在网页「设置」页配置，或复制 .env.example 为 .env 后填写。"
echo

exec "$PY" -m uvicorn app.main:app --port "$PORT"
