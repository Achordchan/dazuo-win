

# 大佐翻译官

一个优雅、高效的跨平台翻译工具，提供多种翻译服务支持和灵活的使用模式。

> 主仓库：<https://github.com/Achordchan/dazuo-win>（代码、Issue、PR 均在 GitHub）。
> Gitee 仓库 `Achordchan/dazuofanyiguan` 长期保留为 Release 镜像：每个版本都需要双端发布，客户端在 GitHub 不可达时会自动改用 Gitee 更新。发布步骤见 [PACKAGING_AND_UPDATE.md](PACKAGING_AND_UPDATE.md) 第 3.1 节。

## 项目介绍

大佐翻译官是一款基于 Python 和 PyQt5 开发的桌面翻译应用程序，支持 Windows、macOS 和 Linux 操作系统。项目采用模块化设计，提供标准窗口和迷你窗口两种使用模式，集成多种翻译引擎，并通过全局快捷键实现便捷的翻译体验。

### 核心特性

- **多翻译引擎**：支持 Google 翻译、微软翻译、DeepL、Achord 内置引擎以及多种 AI 翻译服务（智谱、OpenAI、DeepSeek、通义千问、字节豆包、Google Gemini）
- **双模式界面**：标准窗口模式提供完整功能，迷你窗口模式支持轻量级浮动翻译
- **全局快捷键**：支持自定义快捷键，一键呼出翻译窗口
- **多主题支持**：深色、浅色、粉色三种主题可选
- **系统托盘**：最小化到托盘运行，右键菜单快速操作
- **自动更新**：支持强制更新和可选更新两种模式
- **自动启动**：支持系统开机自启动配置

## 快速开始

### 环境要求

- Python 3.10 或更高版本
- PyQt5
- 必要的依赖包（见 requirements.txt）

### 安装依赖

```bash
# 使用项目自带虚拟环境（推荐）
# Windows:
.venv311\Scripts\activate
# Linux/macOS:
source .venv311/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 运行程序

```bash
# 在项目根目录一键前台运行（Git Bash、Linux 或 macOS）
./start.sh

# 开发调试模式（显示控制台便于查看日志）
./start.sh --debug
```

脚本优先使用项目的 `.venv311`，缺少依赖时会给出安装命令，不会自动安装。程序以前台单进程方式运行，不需要关闭脚本；请在当前终端按 `Ctrl+C`，或在应用托盘中选择“退出”。如需直接运行，仍可使用 `python -m src.main`。

## 功能说明

### 翻译引擎

程序支持以下翻译服务：

| 引擎 | 配置要求 | 说明 |
|------|----------|------|
| Google | 无需配置 | Google 服务在中国大陆无法直接访问，需要能访问海外网站的网络（代理/VPN）；主接口被限流时自动切换备用接口 |
| 微软翻译 | 无需配置 | 默认使用 Bing 翻译网页接口，中国大陆可直接访问；可选填 Azure 翻译 Key / 区域使用官方接口 |
| DeepL | API Key | 支持 DeepL Free / Pro API |
| Achord 内置引擎 | 无需配置 | 本机静默启动的内置引擎（基于 DeepLX） |
| 智谱 AI | API Key | Base URL: https://open.bigmodel.cn/api/paas/v4 |
| OpenAI | API Key | Base URL: https://api.openai.com/v1 |
| DeepSeek | API Key | Base URL: https://api.deepseek.com |
| 通义千问 | API Key | Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1 |
| 字节豆包 | API Key | Base URL: https://ark.cn-beijing.volces.com/api/v3 |
| Google Gemini | API Key | Base URL: https://generativelanguage.googleapis.com/v1beta/openai |

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+Shift+C | 复制并翻译文本 |
| Ctrl+Shift+M | 切换迷你模式/标准模式 |
| Ctrl+Shift+H | 显示/隐藏迷你窗口 |

备用快捷键：
| 快捷键 | 功能 |
|--------|------|
| Ctrl+C,C | 快速呼出翻译窗口 |
| Ctrl+Alt+T | 备用快捷键 |
| Alt+M | 切换 Mini 模式 |
| Alt+H | 显示/隐藏 Mini 窗口 |

### 迷你模式

迷你模式提供轻量级的浮动翻译窗口：

1. 启用迷你模式后，主窗口会隐藏
2. 使用快捷键 Ctrl+Shift+C 可直接翻译剪贴板内容
3. 迷你窗口会自动调整大小以显示完整翻译结果
4. 点击迷你窗口右上角的方框图标可切换回主窗口

### 系统托盘

右键托盘图标可以：
- 显示/隐藏主窗口
- 检查更新
- 查看软件信息
- 退出程序

### 语言选择

- 支持自动语言检测
- 语言下拉支持搜索：下拉菜单首行搜索框，支持中文/拼音/缩写快速定位
- 语言名称使用完整语言名称（如"简体中文"、"繁体中文"、"英语"、"日语"）

## 配置说明

### 配置文件

程序配置存储在用户目录下的配置文件中，包含以下设置：

- 翻译引擎选择
- API 密钥和配置
- 快捷键设置
- 主题选择
- 窗口位置和大小
- 自动启动设置

### AI 服务配置

使用 AI 翻译服务时，需要在设置页面填写：

- 厂家（Vendor）
- 模型 URL（Base URL）
- 模型名（Model）
- API Key

支持按厂家保存配置，切换厂家不会互相覆盖。

## 开发指南

### 项目结构

```
dazuofanyiguan/
├── src/
│   ├── __main__.py          # 程序入口
│   ├── main.py              # 主程序逻辑
│   ├── version.py           # 版本信息
│   ├── gongju/              # 工具模块
│   │   ├── fanyi.py         # 翻译接口抽象
│   │   ├── fanyi_api/       # 翻译引擎实现
│   │   │   ├── google.py    # Google 翻译
│   │   │   ├── microsoft.py # 微软翻译（Bing 网页 / Azure）
│   │   │   ├── deepl.py     # DeepL 翻译
│   │   │   ├── openai_compat.py  # OpenAI 兼容接口
│   │   ├── kuaijiejian.py   # 快捷键监听
│   │   ├── update.py        # 自动更新
│   │   └── autostart.py     # 自启动配置
│   ├── gui/                 # 图形界面
│   │   ├── zhuchuangkou.py  # 主窗口
│   │   ├── mini_chuangkou.py  # 迷你窗口
│   │   ├── shezhi_chuangkou.py  # 设置窗口
│   │   ├── title_bar.py     # 标题栏
│   │   ├── tray.py          # 系统托盘
│   │   ├── themes/          # 主题样式
│   │   └── ...
│   ├── shezhi/              # 配置管理
│   │   └── config.py        # 配置类
│   ├── viewmodels/          # 视图模型
│   │   └── translator_viewmodel.py
│   └── ziyuan/              # 资源文件
│       ├── *.svg            # 图标资源
│       └── changelog.md     # 更新日志
├── requirements.txt         # 依赖列表
├── build.bat               # Windows 打包脚本
├── build.spec              # PyInstaller 配置
├── setup.iss               # Inno Setup 配置
└── README.md               # 说明文档
```

### 核心模块说明

#### 翻译引擎（src/gongju/fanyi）

程序采用策略模式设计翻译功能：

- `FanYiJieKou`：翻译接口抽象基类，定义了翻译接口规范
- `DaZaoFanYi`：翻译管理器，负责协调各翻译服务
- 各翻译引擎实现类：GoogleAPI、MicrosoftAPI、DeepLAPI、AchordBuiltinAPI、OpenAICompatibleAPI

#### 快捷键（src/gongju/kuaijiejian）

- `KuaiJieJianJianTing`：全局快捷键监听类
- `ClipboardDoubleCopyMonitor`：剪贴板双击监控，实现复制翻译功能

#### 配置管理（src/shezhi/config）

- `Config`：配置管理类，负责配置的读取、保存和重置

#### 自动更新（src/gongju/update）

- `Updater`：更新检查和下载类，支持强制更新和可选更新

### 调试技巧

1. 使用 `--debug` 参数启动可查看详细日志
2. 配置信息保存在用户配置目录
3. 窗口位置和大小会自动保存

## 打包发布

### Windows

```bash
# 使用打包脚本
.\build.bat

# 或手动执行
pyinstaller --clean --noconfirm build.spec
```

### 创建安装程序

1. 安装 [Inno Setup](https://jrsoftware.org/isinfo.php)
2. 使用 Inno Setup Compiler 打开 `setup.iss`
3. 点击 "Build" -> "Compile" 或按 Ctrl+F9
4. 生成的安装程序在 `output` 目录中

### macOS

详细打包说明请参考 `MAC_BUILD.md` 文件。

## 更新日志

详细更新日志请查看 `src/ziyuan/changelog.md`。

### v1.2.0 (2025-01-21)

**功能支持**
- 新增迷你窗口功能
- 多主题支持（深色、浅色、粉色）
- 系统托盘功能

**优化改进**
- 翻译速度优化
- 界面响应性提升

**问题修复**
- 修复多个已知问题

## 常见问题

1. **全局快捷键不工作**
   - 不要以管理员身份运行；请检查安全软件是否拦截全局快捷键
   - 检查快捷键是否与其他程序冲突

2. **翻译请求失败**
   - 检查网络连接
   - 验证 API 密钥配置是否正确
   - 确认目标翻译服务可用

3. **迷你窗口不显示**
   - 检查是否启用了迷你模式
   - 尝试使用快捷键 Alt+H 显示窗口

4. **打包失败**
   - 确保在虚拟环境中安装所有依赖
   - 打包路径不要包含中文和空格

## 贡献指南

欢迎提交 Issue 和 Pull Request！

## 许可证

本项目采用 MIT 许可证，详情请查看 LICENSE 文件。

内置翻译引擎基于 DeepLX / OwO Network，遵循 MIT License，Copyright (c) 2022 OwO Network Limited。发行包会随附对应第三方 LICENSE 文件。

## 致谢

感谢所有为这个项目做出贡献的人！
