@echo off
chcp 65001 >nul
set PYTHONUTF8=1

rmdir /s /q build
rmdir /s /q dist
rmdir /s /q dist_nuitka
call .venv311\Scripts\activate.bat
python -m nuitka ^
    --standalone ^
    --windows-disable-console ^
    --output-dir=dist_nuitka ^
    --output-filename="大佐翻译官.exe" ^
    --windows-icon-from-ico=src\ziyuan\logo.ico ^
    --enable-plugin=pyqt5 ^
    --include-qt-plugins=platforms,imageformats,styles ^
    --include-data-dir=src\ziyuan=src\ziyuan ^
    --include-data-dir=src\config=src\config ^
    src\main.py
pause