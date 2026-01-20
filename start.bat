@echo off
cd /d "%~dp0"
call .venv311\Scripts\activate.bat
python src/main.py