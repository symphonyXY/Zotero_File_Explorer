# Zotero File Explorer 1.0.0

本地首版交付日期：2026-11-12。采用选定的新图标，包含现有完整功能和界面优化。
这是可供 GitHub 首次发布使用的本地归档；尚未配置远程仓库或上传资产。

- Setup-x64.exe：Windows x64 当前用户安装器，内置 Python/Qt。
- app/ZoteroFileExplorer/ZoteroFileExplorer.exe：可直接启动，保留整个目录及 _internal，不能只复制 EXE。
- source：同版项目源码 ZIP 与逐文件大小/SHA-256 清单。
- ThirdPartySources：对应 Qt/PySide 源码与 manifest，随再分发保留。
- SHA256SUMS.txt：归档文件的 SHA-256，路径相对本目录。

安装或启动前退出其他目录的程序及托盘实例，以免单实例通信唤起旧进程。
默认运行数据在 LOCALAPPDATA，不会复制或删除 Zotero 原件。
完整测试 137 项通过，封装自检、七档嵌入图标和独立安装卸载通过；完整边界见[版本说明](../../docs/releases/v1.0.0.md)。
已修复重装后快捷方式图标未更新的问题，桌面与开始菜单显式使用独立 ICO；覆盖重装会刷新已有本应用桌面入口。
Windows 10、跨屏 DPI、生产覆盖升级与第三方应用真实拖放仍有未验收范围；安装器未签名。

[首版验证](../../docs/reports/validation-v1.0.0.md) · [归档与发布流程](../README.md)
