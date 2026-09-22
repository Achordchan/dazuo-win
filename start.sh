#!/usr/bin/env bash

set -euo pipefail

project_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$project_root"

python_bin=""
if [[ -n "${PYTHON_BIN:-}" ]]; then
    python_bin="$PYTHON_BIN"
elif [[ -x "$project_root/.venv311/Scripts/python.exe" ]]; then
    python_bin="$project_root/.venv311/Scripts/python.exe"
elif [[ -x "$project_root/.venv311/bin/python" ]]; then
    python_bin="$project_root/.venv311/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
elif command -v python >/dev/null 2>&1; then
    python_bin="python"
else
    echo "错误：未找到 Python 3.10 或更高版本。" >&2
    echo "请先安装 Python，或通过 PYTHON_BIN 指定 Python 可执行文件。" >&2
    exit 1
fi

if [[ "$python_bin" == */* ]]; then
    if [[ ! -x "$python_bin" ]]; then
        echo "错误：Python 可执行文件不存在或不可执行：$python_bin" >&2
        exit 1
    fi
elif ! command -v "$python_bin" >/dev/null 2>&1; then
    echo "错误：无法在 PATH 中找到 Python 命令：$python_bin" >&2
    exit 1
fi

if ! python_version="$("$python_bin" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"; then
    echo "错误：无法运行 Python：$python_bin" >&2
    exit 1
fi

if ! "$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "错误：当前 Python 版本为 $python_version，项目要求 Python 3.10 或更高版本。" >&2
    exit 1
fi

if ! "$python_bin" -c 'import PyQt5, aiohttp, certifi, cryptography, keyboard, openai, pyperclip, qasync, qtawesome' >/dev/null 2>&1; then
    echo "错误：项目运行依赖不完整。" >&2
    printf '请执行："%s" -m pip install -r requirements.txt\n' "$python_bin" >&2
    exit 1
fi

export PYTHONUTF8=1

echo "正在启动大佐翻译官（Python $python_version）..."
echo "停止方式：在当前终端按 Ctrl+C，或在应用托盘中选择“退出”。"
exec "$python_bin" -m src.main "$@"
