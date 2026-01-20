"""
大佐翻译官安装配置
"""
from setuptools import setup, find_packages

setup(
    name="dzfyq",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "PyQt5>=5.15.0",
        "pyperclip>=1.8.0",
        "openai>=1.0.0",
        "qasync>=0.24.0",
        "aiohttp>=3.8.0",
        "PyInstaller==6.3.0",
        "requests==2.31.0",
        "python-dotenv==1.0.0",
        "cryptography==41.0.7",
        "google-cloud-translate==3.12.0",
    ],
    python_requires=">=3.8",
) 