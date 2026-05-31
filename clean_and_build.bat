@echo off
chcp 65001 >nul
set PYTHONUTF8=1

rmdir /s /q build
rmdir /s /q dist
rmdir /s /q dist_nuitka
if not exist ".venv311\Scripts\activate.bat" (
    echo 未找到虚拟环境 .venv311，请先创建并安装依赖。
    exit /b 1
)
call .venv311\Scripts\activate.bat
if errorlevel 1 exit /b 1
python tools\sync_version.py
if errorlevel 1 exit /b 1
python -m nuitka ^
    --standalone ^
    --windows-disable-console ^
    --output-dir=dist_nuitka ^
    --output-filename="大佐翻译官.exe" ^
    --windows-icon-from-ico=src\ziyuan\logo.ico ^
    --enable-plugin=pyqt5 ^
    --include-package-data=qtawesome ^
    --include-qt-plugins=platforms,imageformats,styles ^
    --include-data-dir=src\ziyuan=src\ziyuan ^
    --include-data-dir=src\config=src\config ^
    src\main.py
if errorlevel 1 exit /b 1

for /f "tokens=2 delims==" %%A in ('findstr /b "APP_VERSION" src\version.py') do set VERSION=%%~A
set VERSION=%VERSION:"=%
set VERSION=%VERSION: =%

if not exist output mkdir output
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; if (-not (Test-Path -LiteralPath 'dist_nuitka\main.dist\大佐翻译官.exe' -PathType Leaf)) { throw 'Nuitka output executable missing' }; Compress-Archive -Path 'dist_nuitka\main.dist\*' -DestinationPath 'output\dazuofanyiguan_full.for.windows_%VERSION%.zip' -Force"
if errorlevel 1 exit /b 1
pause
