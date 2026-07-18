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

### 1.2 使用 Nuitka 生成可执行文件
```bash
# 一键脚本
.\build.bat

# 或手动（PowerShell）
$version = python -c "from src.version import APP_VERSION; print(APP_VERSION)"
python -m nuitka `
  --standalone `
  --windows-console-mode=disable `
  --output-dir=dist_nuitka `
  --output-filename="大佐翻译官.exe" `
  --windows-icon-from-ico=src\ziyuan\logo.ico `
  --windows-company-name="大佐翻译官" `
  --windows-product-name="大佐翻译官" `
  --windows-file-description="大佐翻译官" `
  --windows-file-version=$version `
  --windows-product-version=$version `
  --enable-plugin=pyqt5 `
  --include-package-data=qtawesome `
  --include-qt-plugins=platforms,imageformats,styles `
  --include-data-dir=src\ziyuan=src\ziyuan `
  --include-data-dir=src\config=src\config `
  --include-data-files=third_party\deeplx\windows\amd64\deeplx.exe=engines\deeplx\windows\amd64\deeplx.exe `
  --include-data-dir=third_party\deeplx=engines\deeplx `
  src\main.py

python tools\write_update_manifest.py dist_nuitka\main.dist
python tools\create_windows_update_package.py dist_nuitka\main.dist output\dazuofanyiguan_full.for.windows_$version.zip
# 私钥请放在仓库外；也可用环境变量 DZFYQ_UPDATE_PRIVATE_KEY
python tools\sign_windows_update_package.py output\dazuofanyiguan_full.for.windows_$version.zip --version $version --private-key $env:DZFYQ_UPDATE_PRIVATE_KEY
# 默认构建门禁：结构检查 + 用客户端内置公钥验签（错误私钥会在这里失败）
python tools\verify_windows_package.py output\dazuofanyiguan_full.for.windows_$version.zip $version
.\tools\smoke_update_from_1_2_4.ps1 -NewZip output\dazuofanyiguan_full.for.windows_$version.zip -ExpectedVersion $version
```

签名说明：
- Windows 使用 `DZFYQ-SIG-WINDOWS:<base64>`（兼容旧标记 `DZFYQ-SIG:<base64>`）。
- macOS 使用 `DZFYQ-SIG-MACOS:<base64>`。两个平台必须各自签名，不能共用同一条 SIG。
- `tools/sign_windows_update_package.py` 会按包文件名推断 platform/package_type，输出对应标记并写入 `*.sig.json`。
- `build.bat` / `clean_and_build.bat` 在签名后会调用 `tools/verify_windows_package.py`：除检查包结构外，还会读取 `*.zip.sig.json`，用客户端内置公钥验证私钥是否匹配；密钥不匹配时构建失败。
- 发布时把当前版本各平台标记都追加到 Gitee Release 更新说明；需要强制更新时再额外加 `update=1`。

> Windows 在线更新包会把内置引擎打成 `deeplx.exe.payload`，避免 1.2.4 旧更新器覆盖正在运行的 `deeplx.exe` 时回滚；新程序会在缺少 `deeplx.exe` 时自动从 payload 写入用户引擎缓存。

产物位于：`dist_nuitka/`
- `dist_nuitka/main.dist/大佐翻译官.exe`
- `dist_nuitka/main.dist/`（依赖与资源）
- `output/dazuofanyiguan_full.for.windows_<version>.zip`（Windows 在线更新全量包）

### 1.3 使用 Inno Setup 生成安装包
1. 安装 [Inno Setup](https://jrsoftware.org/isinfo.php)
2. 用 Inno Setup Compiler 打开 `setup.iss`
3. 点击 Build → Compile（或 Ctrl+F9）
4. 输出安装包位于 `output/`

`setup.iss` 已配置：
- 中文界面
- 默认安装到当前用户目录：`%LOCALAPPDATA%\Programs\大佐翻译官`
- 沿用旧安装目录，避免已有用户升级时被重新安装到 C 盘并和旧版本并存
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

创建 DMG 后生成 macOS 更新签名：
```bash
version=$(python -c "from src.version import APP_VERSION; print(APP_VERSION)")
python tools/sign_windows_update_package.py \
  dazuofanyiguan.dmg \
  --version "$version" \
  --platform macos \
  --package-type macos_dmg_update \
  --private-key "$DZFYQ_UPDATE_PRIVATE_KEY"
```

使用客户端内置公钥复核刚生成的签名：
```bash
signature=$(python -c 'import json; print(json.load(open("dazuofanyiguan.dmg.sig.json", encoding="utf-8"))["signature"])')
python tools/verify_update_signature.py \
  dazuofanyiguan.dmg \
  --version "$version" \
  --signature "$signature" \
  --filename dazuofanyiguan.dmg \
  --platform macos \
  --package-type macos_dmg_update \
  --print-sha256
```

只有出现 signature-ok 后，才能将输出的 DZFYQ-SIG-MACOS:<base64> 标记写入对应的 Gitee Release 更新说明。

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

### 3.4 强制更新与签名标记
- 在 Release 的更新说明里包含 `update=1` 时视为**强制更新**（未更新将退出）
- Windows 全量更新包还必须在更新说明中包含 `DZFYQ-SIG:<base64>`，由 `tools/sign_windows_update_package.py` 生成
- 缺少签名的更新包会被客户端拒绝

### 3.5 按平台选择安装包
- macOS：选择 `.dmg`
- Windows：只选择与 Release 版本精确匹配的 `dazuofanyiguan_full.for.windows_<version>.zip`
- 若未找到对应资源，会提示错误

### 3.6 下载与安装行为
- 更新包下载到 `~/.dzfyq/update_cache`
- **macOS**：下载后打开 DMG，提示用户手动替换应用
- **Windows**：下载 full zip 后解压到更新缓存目录，启动独立 PowerShell 替换脚本，当前程序退出
- PowerShell 脚本会等待旧进程退出，备份当前安装目录到 `~/.dzfyq/update_backup`，再用全量目录覆盖安装并重启 `大佐翻译官.exe`
- Windows 在线更新不会再启动 `.exe/.msi` 安装器；安装器仅用于首次安装或旧安装迁移

---

## 4. 注意事项
- 打包路径尽量使用英文路径，避免 Qt 插件路径异常
- 打包前确保虚拟环境已安装全部依赖
- 更新依赖 Gitee 可访问性
- Windows 静默替换要求安装目录可写；新安装器默认使用当前用户目录，旧版本若安装在 Program Files，需先用新版安装器迁移一次
- macOS 全局快捷键需要辅助功能权限

---

## 5. 更新 FAQ

**Q1：为什么提示“未找到安装包资源”？**
- Release 里缺少当前平台对应资源：mac 必须 `.dmg`，Windows 必须上传与 Release 版本精确匹配的 `dazuofanyiguan_full.for.windows_<version>.zip`。

**Q2：为什么更新检查失败（403/404）？**
- 403：可能触发频率限制或权限不足。
- 404：仓库地址错误、Release 不存在或仓库不可访问。

**Q3：macOS 为什么下载后不会自动安装？**
- mac 采用 DMG 分发，需要用户手动替换应用，这是系统限制。

**Q4：强制更新是什么？怎么触发？**
- Release 更新说明里包含 `update=1` 即强制更新；拒绝后会退出应用。

**Q5：为什么显示“已是最新版本”但我明明有新包？**
- Release 的 `tag_name` 版本号必须高于当前 `APP_VERSION`，且格式需为 `x.y.z`。

**Q6：Windows 静默更新为什么提示没有写入权限？**
- 静默替换不会拉起安装器，也不会自动提权；如果旧版本安装在 Program Files，请先用新版安装器安装到默认用户目录，之后在线更新即可静默替换。
