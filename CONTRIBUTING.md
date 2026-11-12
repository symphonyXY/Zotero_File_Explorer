# 贡献指南

感谢参与 Zotero File Explorer。开发前阅读[开发手册](docs/development/README.md)和 [AGENTS.md](AGENTS.md)。

## 环境与验证

使用 Windows、Python 3.13 和项目开发锁文件；代码兼容目标为 Python 3.11–3.14。
运行 scripts/dev-setup.ps1，然后运行 scripts/test.ps1。构建步骤见[发布流程](releases/README.md)。
托管 CI 无法认证交互式 Explorer 拖放；涉及 Windows 文件行为的改动必须注明本地验证与未执行项。

## 提交变更

1. Issue 说明问题、复现步骤、预期行为、系统和应用版本；只使用合成数据或已脱敏日志。
2. 保持 src 包和 Qt Widgets 分层；分支建议使用 codex/ 或描述性名称。
3. 对行为变化运行有针对性的回归，再运行 Ruff、完整 pytest、文档与发布树检查。
4. 同步唯一权威文档和 CHANGELOG 的 Unreleased，说明兼容性、验证结果与剩余限制。
5. PR 保持范围清楚，说明最终行为；不要提交虚拟环境、构建输出、附件、索引、凭据或个人目录。

不可退化的边界：只读 Zotero、保留原附件、后台查询/路径验证、GUI 线程更新 Qt、原生 local URL / CF_HDROP / CopyAction。
每项任务按[维护清单](docs/development/maintenance.md)检查生成物，未知文件保留。

[返回项目首页](README.md) · [开发手册](docs/development/README.md)
