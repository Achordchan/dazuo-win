@echo off
chcp 65001 >nul
set PYTHONUTF8=1

echo 清理旧的构建文件...
rmdir /s /q build
rmdir /s /q dist
rmdir /s /q dist_nuitka

echo 激活虚拟环境...
if not exist ".venv311\Scripts\activate.bat" (
    echo 未找到虚拟环境 .venv311，请先创建并安装依赖。
    exit /b 1
)
call .venv311\Scripts\activate.bat
if errorlevel 1 exit /b 1

echo 同步版本信息...
python tools\sync_version.py
if errorlevel 1 exit /b 1

echo 开始打包...
python -m nuitka ^
    --standalone ^
    --windows-disable-console ^
    --mingw64 ^
    --assume-yes-for-downloads ^
    --output-dir=dist_nuitka ^
    --output-filename="大佐翻译官.exe" ^
    --windows-icon-from-ico=src\ziyuan\logo.ico ^
    --enable-plugin=pyqt5 ^
    --include-package-data=qtawesome ^
    --include-qt-plugins=platforms,imageformats,styles ^
    --include-data-dir=src\ziyuan=src\ziyuan ^
    --include-data-dir=src\config=src\config ^
    --include-data-files=third_party\deeplx\windows\amd64\deeplx.exe=engines\deeplx\windows\amd64\deeplx.exe ^
    --include-data-dir=third_party\deeplx=engines\deeplx ^
    src\main.py
if errorlevel 1 exit /b 1

for /f "tokens=2 delims==" %%A in ('findstr /b "APP_VERSION" src\version.py') do set VERSION=%%~A
set VERSION=%VERSION:"=%
set VERSION=%VERSION: =%

if not exist output mkdir output
echo 生成 Windows 全量静默更新包...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; if (-not (Test-Path -LiteralPath 'dist_nuitka\main.dist\大佐翻译官.exe' -PathType Leaf)) { throw 'Nuitka output executable missing' }; Compress-Archive -Path 'dist_nuitka\main.dist\*' -DestinationPath 'output\dazuofanyiguan_full.for.windows_%VERSION%.zip' -Force"
if errorlevel 1 exit /b 1

echo 构建完成！
echo - 在线更新包：output\dazuofanyiguan_full.for.windows_%VERSION%.zip
echo - 首次安装包：可继续使用 Inno Setup Compiler 编译 setup.iss
pause
