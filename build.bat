@echo off
chcp 65001 >nul
set PYTHONUTF8=1

echo Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist dist_nuitka rmdir /s /q dist_nuitka

echo Activating virtual environment...
if not exist ".venv311\Scripts\activate.bat" (
    echo Missing .venv311 virtual environment. Create it and install dependencies first.
    exit /b 1
)
call .venv311\Scripts\activate.bat
if errorlevel 1 exit /b 1

echo Syncing version files...
python tools\sync_version.py
if errorlevel 1 exit /b 1

for /f "tokens=2 delims==" %%A in ('findstr /b "APP_VERSION" src\version.py') do set VERSION=%%~A
set VERSION=%VERSION:"=%
set VERSION=%VERSION: =%

echo Building with Nuitka...
python -m nuitka ^
    --standalone ^
    --windows-disable-console ^
    --windows-file-version=%VERSION% ^
    --windows-product-version=%VERSION% ^
    --windows-company-name="大佐软件" ^
    --windows-product-name="大佐翻译官" ^
    --windows-file-description="大佐翻译官" ^
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

echo Writing update manifest...
python tools\write_update_manifest.py dist_nuitka\main.dist
if errorlevel 1 exit /b 1

if not exist output mkdir output
echo Creating Windows full update package...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; if (-not (Test-Path -LiteralPath 'dist_nuitka\main.dist\大佐翻译官.exe' -PathType Leaf)) { throw 'Nuitka output executable missing' }; Compress-Archive -Path 'dist_nuitka\main.dist\*' -DestinationPath 'output\dazuofanyiguan_full.for.windows_%VERSION%.zip' -Force"
if errorlevel 1 exit /b 1

echo Build complete.
echo - Full update package: output\dazuofanyiguan_full.for.windows_%VERSION%.zip
echo - Setup package: compile setup.iss with Inno Setup Compiler
pause
