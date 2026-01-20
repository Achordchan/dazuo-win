@echo off
echo 清理旧的构建文件...
rmdir /s /q build
rmdir /s /q dist

echo 激活虚拟环境...
call .venv311\Scripts\activate.bat

echo 开始打包...
pyinstaller --clean --noconfirm build.spec

echo 构建完成！
echo 现在你可以使用 Inno Setup Compiler 编译 setup.iss 文件来创建安装程序。
pause