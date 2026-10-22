@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ==========================================================================
REM  赛博女友 CyberGirlfriend - 一键安装依赖并启动（Windows）
REM  用法：双击本文件，或在项目根目录执行  scripts\run.bat
REM ==========================================================================

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%..\backend"
set "PORT=8000"

echo.
echo ==========================================================
echo   赛博女友 CyberGirlfriend - 启动脚本
echo ==========================================================
echo.

if not exist "%BACKEND_DIR%\app\main.py" (
    echo [错误] 未找到后端目录：%BACKEND_DIR%
    echo        请确认本脚本位于项目的 scripts\ 目录下。
    pause
    exit /b 1
)

pushd "%BACKEND_DIR%"

REM ---------- 1. 检查 Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 python，请先安装 Python 3.10+ 并加入 PATH。
    echo        下载地址：https://www.python.org/downloads/
    popd
    pause
    exit /b 1
)

for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])" 2^>nul') do set "PYVER=%%v"
echo [1/4] Python 版本：!PYVER!

REM ---------- 2. 创建 / 激活虚拟环境 ----------
if not exist ".venv\Scripts\python.exe" (
    echo [2/4] 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败。
        popd
        pause
        exit /b 1
    )
) else (
    echo [2/4] 复用已有虚拟环境 .venv
)
set "PY=.venv\Scripts\python.exe"

REM ---------- 3. 安装依赖 ----------
echo [3/4] 安装依赖（首次较慢，请耐心等待）...
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败，请检查网络或 pip 配置。
    echo        可手动执行： "%PY%" -m pip install -r requirements.txt
    popd
    pause
    exit /b 1
)

REM ---------- 4. 启动服务 ----------
echo [4/4] 启动服务： http://localhost:%PORT%
echo.
echo   访问地址： http://localhost:%PORT%
echo   接口文档： http://localhost:%PORT%/docs
echo   停止服务： 在本窗口按 Ctrl + C
echo.
echo   当前默认使用 mock 演示模型，无需任何 API Key。
echo   若需真实模型，请在网页「设置」页配置，或复制 .env.example 为 .env 后填写。
echo.

start "" http://localhost:%PORT%
"%PY%" -m uvicorn app.main:app --port %PORT%

popd
endlocal
