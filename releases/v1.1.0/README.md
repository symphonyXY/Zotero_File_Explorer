# Zotero File Explorer 1.1.0

2026-11-18 Windows x64 最终本地交付。

## 安装与运行

从托盘退出 Explorer，运行 ZoteroFileExplorer-1.1.0-Setup-x64.exe。
也可运行 app/ZoteroFileExplorer/ZoteroFileExplorer.exe，请保留完整应用目录。

[安装说明](app/ZoteroFileExplorer/docs/user/installation.md) · [使用指南](app/ZoteroFileExplorer/docs/user/user-guide.md)

## 本版变化

- 支持文献速览卡的创建、Markdown 编辑、预览、草稿恢复与手动复习。
- 卡片通过 Zotero 存储型附件同步，使用 Zotero 已配置的 WebDAV。
- Windows 应用列表单独显示产品名和版本号。
- 移除“文献库与分类”选中行左侧的蓝色括号状装饰。
- 安装包包含用户指南，应用源码包包含生产源码、构建脚本与许可。

## 文件与校验

source 包含本版应用源码及构建说明。ThirdPartySources 包含随应用分发的 Qt/PySide 对应源码，再分发时请一并保留。
SHA256SUMS.txt 提供安装器、应用目录、源码和许可材料的逐文件 SHA-256。

## 验证与适用范围

Windows 11 上通过 149 项源码回归及静态检查。浅色、深色、分类选择与展开通过验证。
最终安装载荷通过独立 AppId 的安装、重装、快捷方式、自检和卸载验证。
Zotero 文件同步已在同机两个独立 Zotero 10.0.8 配置上验证。
Windows 10、跨物理设备同步和生产覆盖升级尚待实测。安装器尚未签名。
