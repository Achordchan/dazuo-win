# 打包与更新流程说明

> 面向发布人员/维护者。此文档整理 Windows/macOS 的打包与在线更新机制。

## 1. Windows 打包流程

### 1.1 依赖准备
```bash
# 进入项目根目录
# 启用虚拟环境（推荐）
.venv311\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 1.2 使用 PyInstaller 生成可执行文件
```bash
# 一键脚本
.\build.bat

# 或手动
pyinstaller --clean --noconfirm build.spec
```

`build.spec` 已配置：
- 打包为单个 exe
- 自动包含资源文件
- 设置程序图标
- 隐藏控制台窗口

产物位于：`dist/`

### 1.3 使用 Inno Setup 生成安装包
1. 安装 [Inno Setup](https://jrsoftware.org/isinfo.php)
2. 用 Inno Setup Compiler 打开 `setup.iss`
3. 点击 Build → Compile（或 Ctrl+F9）
4. 输出安装包位于 `output/`

`setup.iss` 已配置：
- 中文界面
- 程序图标
- 开始菜单快捷方式
- 桌面快捷方式（可选）
- 卸载入口

---

## 2. macOS 打包流程

> 必须在 macOS 上执行，Windows 无法生成 `.app/.dmg`。

### 2.1 准备工程目录（推荐英文路径）
```bash
mkdir -p ~/build/dazuofanyiguan
# 将项目复制到该目录
```

### 2.2 创建虚拟环境并安装依赖
```bash
cd ~/build/dazuofanyiguan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.3 准备图标（.icns）
将图标放到：
```
src/ziyuan/logo.icns
```
如只有 `.png`，可用如下命令生成：
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

### 2.4 PyInstaller 打包为 .app
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

### 2.5 （可选）生成 DMG
```bash
brew install create-dmg

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

---

## 3. 在线更新流程（当前实现）

### 3.1 更新源
- 使用 Gitee Release 最新版本：
  `https://gitee.com/api/v5/repos/Achordchan/dazuofanyiguan/releases/latest`

### 3.2 更新触发
- 手动：设置页 “检测更新”
- 自动：应用启动后延迟触发（主窗口内定时检查）

### 3.3 版本判断
- 比较 `tag_name` 与当前 `APP_VERSION`
- 若版本更新，则进入下载流程

### 3.4 强制更新标记
- 在 Release 的更新说明里包含 `update=1`
- 命中后视为**强制更新**（未更新将退出）

### 3.5 按平台选择安装包
- macOS：选择 `.dmg`
- Windows：选择 `.exe` / `.msi`
- 若未找到对应资源，会提示错误

### 3.6 下载与安装行为
- 安装包下载到临时目录
- **macOS**：下载后打开 DMG，提示用户手动替换应用
- **Windows**：下载后启动安装包并退出当前程序

---

## 4. 注意事项
- 打包路径尽量使用英文路径，避免 Qt 插件路径异常
- 打包前确保虚拟环境已安装全部依赖
- 更新依赖 Gitee 可访问性
- macOS 全局快捷键需要辅助功能权限

---

## 5. 更新 FAQ

**Q1：为什么提示“未找到安装包资源”？**
- Release 里缺少当前平台对应后缀：mac 必须 `.dmg`，Windows 必须 `.exe/.msi`。

**Q2：为什么更新检查失败（403/404）？**
- 403：可能触发频率限制或权限不足。
- 404：仓库地址错误、Release 不存在或仓库不可访问。

**Q3：macOS 为什么下载后不会自动安装？**
- mac 采用 DMG 分发，需要用户手动替换应用，这是系统限制。

**Q4：强制更新是什么？怎么触发？**
- Release 更新说明里包含 `update=1` 即强制更新；拒绝后会退出应用。

**Q5：为什么显示“已是最新版本”但我明明有新包？**
- Release 的 `tag_name` 版本号必须高于当前 `APP_VERSION`，且格式需为 `x.y.z`。
