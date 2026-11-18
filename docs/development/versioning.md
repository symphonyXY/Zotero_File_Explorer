# 版本与 Git 历史

## 首版

当前唯一首版为 1.0.0，以项目所有者选定新图标后的完整程序为基线，本地交付日期为 2026-11-12。
main 保存公开源码，首版交付保存在本地 releases/v1.0.0。日常开发保留提交历史，未经明确授权不重置或强制推送。

## 版本规则

- PATCH 用于兼容修复；MINOR 用于兼容新能力；MAJOR 用于破坏性变化。
- 版本源是 src/zotero_file_explorer/__init__.py，pyproject 动态读取，ISS 默认值同步。
- 每次变化同步唯一权威专题文档与 CHANGELOG Unreleased；例行维护不自动升版。
- 发布从已审查源码构建，记录源码指纹、实际验证和已知限制；本地交付与 GitHub 在线发布分别记录。
- 每个版本在 docs/releases/vX.Y.Z.md 说明变化原因、行为、扩展位置、兼容性及验证边界。
- 本地二进制归档在 releases/vX.Y.Z；不进入普通 Git 历史。

[返回开发手册](README.md) · [版本索引](../releases/README.md) · [发布流程](../../releases/README.md)
