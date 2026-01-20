# mac 打包说明（大佐翻译官）

> 必须在 macOS 上执行。Windows 无法生成 mac 的 .app/.dmg。

## 1. 准备工程目录（英文路径）
建议放在英文路径，避免 PyQt/Qt 路径乱码问题：

```bash
mkdir -p ~/build/dazuofanyiguan
# 把项目复制到此目录
```

## 2. 创建虚拟环境并安装依赖
```bash
cd ~/build/dazuofanyiguan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. 准备图标（.icns）
mac 需要 .icns 文件。把图标放到：

```
src/ziyuan/logo.icns
```

如果你只有 .png，可以用下面命令生成：

```bash
mkdir -p build/icon.iconset
sips -z 16 16     src/ziyuan/logo.png --out build/icon.iconset/icon_16x16.png
sips -z 32 32     src/ziyuan/logo.png --out build/icon.iconset/icon_16x16@2x.png
sips -z 32 32     src/ziyuan/logo.png --out build/icon.iconset/icon_32x32.png
sips -z 64 64     src/ziyuan/logo.png --out build/icon.iconset/icon_32x32@2x.png
sips -z 128 128   src/ziyuan/logo.png --out build/icon.iconset/icon_128x128.png
sips -z 256 256   src/ziyuan/logo.png --out build/icon.iconset/icon_128x128@2x.png
sips -z 256 256   src/ziyuan/logo.png --out build/icon.iconset/icon_256x256.png
sips -z 512 512   src/ziyuan/logo.png --out build/icon.iconset/icon_256x256@2x.png
sips -z 512 512   src/ziyuan/logo.png --out build/icon.iconset/icon_512x512.png
sips -z 1024 1024 src/ziyuan/logo.png --out build/icon.iconset/icon_512x512@2x.png
iconutil -c icns build/icon.iconset -o src/ziyuan/logo.icns
```

> 如果你已有 logo.icns，可跳过本步。

## 4. PyInstaller 打包成 .app
```bash
pyinstaller --clean --noconfirm \
  --windowed \
  --icon=src/ziyuan/logo.icns \
  --add-data "src/ziyuan:src/ziyuan" \
  --add-data "src/config:src/config" \
  --hidden-import=PyQt5.QtSvg \
  --hidden-import=aiohttp \
  --hidden-import=openai \
  --hidden-import=keyboard \
  --hidden-import=pyperclip \
  --hidden-import=qasync \
  --hidden-import=cryptography \
  --name "大佐翻译官" \
  src/main.py
```

产物：
```
dist/大佐翻译官.app
```

## 5. （可选）生成 DMG 安装包
```bash
brew install create-dmg
```

```bash
create-dmg \
  --volname "dazuofanyiguan" \
  --window-pos 200 120 \
  --window-size 600 300 \
  --app-drop-link 450 150 \
  "dazuofanyiguan.dmg" \
  "dist/大佐翻译官.app"
```

产物：
```
dazuofanyiguan.dmg
```

## 6. （可选）签名与公证
如果要在 mac 上避免“未知开发者”拦截，需要 Apple 开发者证书。需要时再补充命令。

---

## 常见问题
1. **必须英文路径**：中文路径可能导致 Qt 插件路径乱码。
2. **资源路径**：打包后资源必须通过运行时路径或 Qt 资源系统访问，不能写死固定磁盘路径。
