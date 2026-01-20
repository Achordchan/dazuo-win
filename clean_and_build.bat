@echo off
rmdir /s /q build
rmdir /s /q dist
call .venv311\Scripts\activate.bat
pyinstaller --clean ^
    --noconfirm ^
    --windowed ^
    --icon="src\ziyuan\logo.ico" ^
    --add-data "src/ziyuan;src/ziyuan" ^
    --hidden-import=PyQt5.QtSvg ^
    --hidden-import=aiohttp ^
    --hidden-import=openai ^
    --hidden-import=keyboard ^
    --hidden-import=pyperclip ^
    --hidden-import=qasync ^
    --hidden-import=cryptography ^
    --name "大佐翻译官" ^
    "src/main.py"
pause