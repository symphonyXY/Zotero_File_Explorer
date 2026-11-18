<p align="center">
  <img src="assets/icons/app.png" width="112" alt="Zotero File Explorer 图标">
</p>

# Zotero File Explorer

**在 Windows 上搜索、浏览和复制 Zotero 原始附件。**

通过 Zotero Local API 获取文献，在本地快速检索，并把真实附件复制或拖放到其他应用。
直接使用已有文件，不修改 Zotero 数据库，不搬移原件，也不建立第二套附件库。

A Windows desktop browser for Zotero attachments with local search, native drag-and-drop and Markdown Paper Cards.

## 功能

- **文献速览卡（1.1.0）**：在个人文献库创建 Markdown 子附件，编辑、预览和主动回忆。保存需 Zotero 10+ 本地写入授权，附件使用 Zotero 已配置的同步方式。[使用速览卡](docs/user/user-guide.md#文献速览卡)

- **检索与浏览**：标题、作者、年份、DOI、标签、文件名搜索；按文献库、分类和文件类型筛选。
- **附件管理视图**：展开多附件，区分原件、翻译及加工产物；支持人工确认主附件和分类。
- **真实文件操作**：打开、复制文件、复制路径、定位文件夹；多选和拖放只提供复制动作。
- **快捷窗口**：全局热键唤出、自动聚焦搜索，使用方向键和 Enter 操作。
- **本地体验**：离线缓存、中英文、深浅主题、布局记忆及尊重 Windows 偏好的可关闭动画。

## 安装与开始使用

Paper Cards 的 Windows 安装包为 **1.1.0**。[本版说明](docs/releases/v1.1.0.md)列出变更与验证范围。首版保存在 `releases/v1.0.0/`。
源码仓库不包含安装器、Python 虚拟环境或用户文献。

1. 从托盘退出旧版 Explorer，运行 `ZoteroFileExplorer-1.1.0-Setup-x64.exe`，按当前用户安装，无需另装 Python。
2. 打开 Zotero，在“设置 → 高级”中开启“允许本机其他应用程序与 Zotero 通信”。
3. 启动本程序，点击“立即同步”，随后搜索或选择文献。
4. 使用 Ctrl+C 复制真实附件，再到目标应用粘贴；也可直接拖放。

目标平台为 Windows 10 1809+ / Windows 11 x64；当前实机验证为 Windows 11。
安装、数据目录与卸载说明见[安装指南](docs/user/installation.md)。

## 操作

主窗口与快捷窗口的操作见[用户指南](docs/user/user-guide.md)。

| 操作 | 快捷键 |
|---|---|
| 唤出快捷窗口 | Ctrl+Alt+Z，可在设置中更改 |
| 聚焦主窗口搜索框 | Ctrl+F |
| 从搜索框进入结果 | Down |
| 打开当前附件 | Enter 或双击 |
| 复制选中的原件 | Ctrl+C |
| 隐藏快捷窗口 / 退出应用 | Escape / Ctrl+Q |

## 从源码运行

支持 Python 3.11–3.14，当前验证环境使用 Python 3.13。界面采用 PySide6 / Qt Widgets。
在工程根目录运行 PowerShell：

```powershell
.\scripts\dev-setup.ps1
.\.venv\Scripts\python.exe -m zotero_file_explorer
```

检查源码、文档和测试：

```powershell
.\scripts\test.ps1
```

打包需 Inno Setup，步骤见[构建与发布](releases/README.md)。

## 工程组织

```text
src/zotero_file_explorer/  领域、只读 API、服务、存储、Windows 集成与 Qt 界面
assets/icons/             正式图标源图、PNG 和多尺寸 ICO
tests/                    单元、Qt 集成、Windows 原生文件行为测试
scripts/                  开发、验证、构建、归档与安全清理工具
installer/                PyInstaller 和 Inno Setup 定义
docs/                     使用、开发、版本说明与本版验证证据
licenses/                 第三方许可与归属材料
.github/                  Windows CI、Issue 和 PR 模板
releases/                 本地版本归档；二进制不进入普通 Git 历史
```

[文档导航](docs/README.md) · [开发手册](docs/development/README.md) · [贡献指南](CONTRIBUTING.md) · [安全报告](SECURITY.md)

## 边界与许可

本程序不编辑文献、不解析 Zotero 原始数据库、不执行 PDF 翻译或云端同步。
拖放接收能力取决于目标应用。已知兼容性范围见[版本说明](docs/releases/README.md)。

应用代码和项目图标采用 [MIT](LICENSE)。Qt/PySide 等组件保留各自许可；再分发二进制时保留[第三方说明](THIRD_PARTY_NOTICES.md)及对应源码材料。
这是独立项目，非 Zotero 官方产品；新图标不代表 Zotero 官方标识或背书。
