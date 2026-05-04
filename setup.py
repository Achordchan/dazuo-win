"""
大佐翻译官安装配置
"""
from setuptools import setup, find_packages

setup(
    name="dzfyq",
    version="1.2.3",
    packages=find_packages(),
    install_requires=[
        "PyQt5>=5.15.0",
        "pyperclip>=1.8.0",
        "openai>=1.0.0",
        "qasync>=0.24.0",
        "aiohttp>=3.8.0",
        "qtawesome>=1.4.2",
        "PyInstaller==6.3.0",
    ],
    python_requires=">=3.8",
)
