# -*- mode: python ; coding: utf-8 -*-
import os
from glob import glob

block_cipher = None

# 获取当前目录
current_dir = os.getcwd()

# 收集资源文件
resource_files = []
src_resource_dir = os.path.join(current_dir, 'src', 'ziyuan')
if os.path.exists(src_resource_dir):
    for file in glob(os.path.join(src_resource_dir, '*.*')):
        dest_path = os.path.join('src', 'ziyuan')
        resource_files.append((file, dest_path))

# 收集配置文件
config_files = []
src_config_dir = os.path.join(current_dir, 'src', 'config')
if os.path.exists(src_config_dir):
    for file in glob(os.path.join(src_config_dir, '*.*')):
        dest_path = os.path.join('src', 'config')
        config_files.append((file, dest_path))

# 收集字体文件
font_files = []
src_font_dir = os.path.join(current_dir, 'src', 'font')
if os.path.exists(src_font_dir):
    for file in glob(os.path.join(src_font_dir, '*.*')):
        dest_path = os.path.join('src', 'font')
        font_files.append((file, dest_path))

print("Resource files to be included:", resource_files)
print("Config files to be included:", config_files)
print("Font files to be included:", font_files)

engine_files = []
engine_dir = os.path.join(current_dir, 'third_party', 'deeplx')
if os.path.exists(engine_dir):
    for root, _, files in os.walk(engine_dir):
        for file in files:
            source_path = os.path.join(root, file)
            relative_dir = os.path.relpath(root, engine_dir)
            dest_path = os.path.join('engines', 'deeplx', relative_dir)
            engine_files.append((source_path, dest_path))

print("Engine files to be included:", engine_files)

# 合并所有数据文件
all_data_files = resource_files + config_files + font_files + engine_files

a = Analysis(
    ['src/main.py'],
    pathex=[current_dir],
    binaries=[],
    datas=all_data_files,
    hiddenimports=[
        'PyQt5',
        'PyQt5.QtSvg',
        'aiohttp',
        'openai',
        'keyboard',
        'pyperclip',
        'qasync'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'google',
        'grpc',
        'protobuf',
        'cryptography',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='大佐翻译官',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(current_dir, 'src', 'ziyuan', 'logo.ico'),
    version='file_version_info.txt',
    uac_admin=False,
)
