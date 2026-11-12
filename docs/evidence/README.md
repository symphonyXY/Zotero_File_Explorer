# 首版证据

本目录只保留当前 1.0.0 验证与第三方来源材料。公开截图在 docs/images，均使用合成数据。

| 文件 | 用途 |
|---|---|
| icon.json | 正式图标源图、输出哈希、多尺寸和 Qt 加载结果 |
| tests-1.0.0.xml | 本版完整 pytest，公开副本移除主机名 |
| package-1.0.0.json | 重新构建的 EXE/安装器、自检、资源与 DLL 记录 |
| build-sources-1.0.0.json | 构建时源码、脚本和安装定义指纹 |
| installer-1.0.0.json | 独立安装/重装、旧快捷方式图标迁移、自检、卸载及本机覆盖安装核对 |
| third-party-sources.json | 再分发的对应第三方源码及哈希 |
| research-sources.json | 当前协议和分类实现参考的上游快照、源码链接与已有哈希 |

含本机路径的清理清单保存在本地 work/cleanup，不进入源码包。

[验证报告](../reports/validation-v1.0.0.md) · [开发手册](../development/README.md) · [文档导航](../README.md)
