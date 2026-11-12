# 1.0.0 验证报告

日期：2026-11-12。对象是选定新图标后的首版源码与重新构建的程序。
## 通过的检查

- Ruff、完整 pytest **137 通过，0 失败/跳过**，包括实时 Qt/固化剪贴板两种原生 Shell 接收端路径、CF_HDROP、CopyAction、多选和身份恢复。
- 文档链接、公开树和 pip check 通过；原始测试日志保存在本地 work，公开 [XML](../evidence/tests-1.0.0.xml)移除主机名。
- PyInstaller + Inno Setup 从本版源码重建；封装 EXE 在 System32-only PATH、清除 Python 环境变量后自检通过。
- EXE 和安装器内的七档 RT_ICON 图像字节均与新 ICO 匹配；打包 PNG/ICO 与源码相同，没有混入候选稿和源图。
- 独立 AcceptanceTest AppId 验证首次安装不选桌面、同名外部快捷方式保留、选中创建、旧默认图标在未选桌面重装时迁移；桌面/开始菜单的实际 .lnk 目标、独立 ICO 哈希、自检、EXE 哈希及卸载通过，卸载保留测试数据。
- 以修复安装器在本机现有安装目录执行覆盖重装，退出码 0；桌面与两个开始菜单快捷方式均引用与源 ICO 相同哈希的文件，资源管理器实际显示与源图一致。未清空全局图标缓存或重启 Explorer。
- Windows 11 build 26200 / Python 3.13.17 / PySide6 6.10.2，源界面以 150% 缩放合成数据截图复核；鼠标单选/Ctrl 多选、Down、Ctrl+C、Escape 与重开聚焦通过。
- 使用 computer-use 查看封装窗口的新标题栏/品牌图标，并验证快捷窗口聚焦、键盘选择、就地复制回执及退出。测试仅使用合成库和 no-sync。
- 源码、脚本和安装定义的构建指纹与最终工作树复核；项目源码 ZIP 逐文件核对，归档副本按 SHA-256 校验。

封装的[机器记录](../evidence/package-1.0.0.json)、[来源指纹](../evidence/build-sources-1.0.0.json)和[安装记录](../evidence/installer-1.0.0.json)与本版交付对应。

## 未执行与限制

Windows 10、生产覆盖升级、100%/200%/跨屏 DPI、干净断网机器、真实输入法候选窗口、屏幕阅读器、真实 Zotero 同步、跨应用鼠标拖放、长稳、代码签名与 compositor/display FPS 未全面验收。
本版没有三档性能对照结论，不宣称显示帧率提升。自动 MIME/Shell 接收端测试不替代真实目标应用验收。

## 交付完整性

唯一正式交付入口为 releases/v1.0.0。安装器、完整运行目录、项目源码与第三方源包通过 SHA-256 校验；每项证据保留在 docs/evidence。
开发环境和可复用构建工具保留。本地临时工作区可在归档验证后清理，清单位于 work/cleanup，不进入公开源码。

[报告索引](README.md) · [测试流程](../development/testing.md) · [证据索引](../evidence/README.md)
