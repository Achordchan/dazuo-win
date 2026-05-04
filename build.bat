@echo off
chcp 65001 >nul
set PYTHONUTF8=1

echo 清理旧的构建文件...
rmdir /s /q build
rmdir /s /q dist
rmdir /s /q dist_nuitka

echo 激活虚拟环境...
call .venv311\Scripts\activate.bat

echo 开始打包...
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

echo 构建完成！
echo 现在你可以使用 Inno Setup Compiler 编译 setup.iss 文件来创建安装程序。
pause
