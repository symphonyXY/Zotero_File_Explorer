# 安装与运行

包含速览卡的本地安装包位于 `releases/v1.1.0/`，首版归档位于 `releases/v1.0.0/`。参见[本版说明](../releases/v1.1.0.md)。

## 环境

目标平台为 Windows 10 1809+ / Windows 11 x64，实机验证为 Windows 11。
通过 Zotero 本机 API 工作。文献速览卡支持 Zotero 10 或更新版本的个人库。
安装包自带 Python/Qt，无需另装运行库。代码签名尚未完成。

## 安装或直接运行

安装前退出已有 Explorer 程序及托盘实例，运行 ZoteroFileExplorer-1.1.0-Setup-x64.exe，按当前用户安装。
开始菜单提供主窗口与快捷窗口，桌面快捷方式可选；开机启动默认关闭。
重装会更新已有、目标属于本安装目录的桌面快捷方式，即使未重新勾选桌面选项。
快捷方式使用随安装包提供的独立图标，安装结束会通知 Windows 刷新；无须清空系统图标缓存。
也可运行归档中 app/ZoteroFileExplorer/ZoteroFileExplorer.exe，但必须保留 _internal 和其余同目录文件。
程序数据仍在 LOCALAPPDATA 下，此目录运行方式不等于设置随身的便携模式。

启动 Zotero，在“设置 → 高级”开启允许本机其他应用通信，回到程序点击立即同步。
无需 Zotero 账号密码或云 API Key。运行数据默认在 `%LOCALAPPDATA%\ZoteroFileExplorer`。
单实例机制可能唤起仍在运行的其他目录程序，因此更换程序前应先退出旧实例。

## 卸载与后续升级

卸载保留本应用索引和设置；不操作 Zotero 目录或附件。
升级前可备份本应用数据目录，按版本说明操作并核对交付校验值。生产覆盖升级未全面验收。
需要完整删除运行数据时，由用户自行确认；不要删除 Zotero 数据。

[使用指南](user-guide.md) · [构建发布](../../releases/README.md) · [文档导航](../README.md)
