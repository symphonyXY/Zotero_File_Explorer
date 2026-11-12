# 总开发文档

当前首版为采用新图标的 [v1.0.0](../releases/v1.0.0.md)，该页记录完整能力、扩展位置及优化方向。后续每个版本按[版本规则](versioning.md)说明增量。

## 开发目标和技术栈

构建只读、响应及时的 Zotero 原始附件桌面浏览器；保护原件并保留 Windows 原生复制/拖放。
Python 支持 3.11–3.14，开发脚本默认使用 3.13；PySide6-Essentials 6.10.2、Qt Widgets、QTreeView、QThreadPool、SQLite。
依赖以 [pyproject.toml](../../pyproject.toml) 和 [requirements-dev.lock](../../requirements-dev.lock) 为准。
没有应用 QML 树，不引入无用 UI 框架。

## 架构与职责

只读 API → 同步/分类 → 本应用元数据索引 → 后台搜索 → Qt 视图 → 原生文件接口。

| 模块（src/zotero_file_explorer 下） | 职责 |
|---|---|
| core | 数据模型、原件/译件分类 |
| api | 只读 Zotero Local API |
| services | 同步、真实路径解析与验证 |
| storage | 只管理本应用配置、覆盖设置与索引 |
| platform | Windows 文件、热键、剪贴板与系统偏好 |
| ui | 视图、模型、后台信号、动画 |
| i18n | 中英文文案 |
| app.py | 应用控制器和生命周期协调 |

细节见[架构](architecture.md)与[Zotero 集成](zotero-integration.md)。

## 开发环境

以下命令均从仓库根目录在 PowerShell 执行；已有 `.venv` 保留。

```powershell
.\scripts\dev-setup.ps1
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m zotero_file_explorer
```

仅验证时使用隔离数据，不触及用户配置：

```powershell
.\.venv\Scripts\python.exe -m zotero_file_explorer --data-dir build/dev-smoke --no-sync --smoke-test
```

## 标准目录

```text
.github/workflows/            Windows CI
assets/icons/                 正式运行图标
config/                       默认配置
src/zotero_file_explorer/      现有 Python 包
installer/                    PyInstaller、Inno Setup 定义
scripts/                      构建、测试、文档检查、清理和诊断
licenses/                     第三方许可及对应材料
tests/unit/                   领域、存储和工程安全测试
tests/integration/            API、Qt、Windows、响应性测试
tests/fixtures/               测试夹具说明
docs/development/             总开发文档与专题规范
docs/user/                    安装及使用
docs/releases/                逐版本说明
docs/reports/                 当前版本验证报告
docs/images/                  合成数据界面截图
docs/evidence/                经审查的可公开证据
releases/README.md            正式发布归档规则
```

根目录还有 README、AGENTS、CHANGELOG、LICENSE、THIRD_PARTY_NOTICES、pyproject、锁文件及 Git 配置。
`.venv`、`build`、`dist`、`work`、`backups` 和缓存是本地目录，不属于正式 Git 树。
不为模板新建空 QML、images、gui 或 performance 目录；当前 GUI 测试在 integration，性能工具在 scripts。

## 标准开发流程

1. 读取 [AGENTS](../../AGENTS.md)，检查 Git 状态及用户现有改动；结构变更前做限定范围恢复检查点。
2. 按[编码规范](coding-standards.md)实施；视图改动同时遵循[UI](ui-design.md)与[动画](animation-spec.md)。
3. 执行[测试流程](testing.md)，保留失败证据，按变更范围验证真实 MIME、选择状态或打包资源。
4. 更新唯一权威专题文档与相对链接；用户可感知改动记入 [Unreleased](../../CHANGELOG.md)。维护任务不强制升版。
5. 构建先过门禁，发布按[发布流程](../../releases/README.md)归档，创建逐版本说明；不得虚构发布状态。
6. 每项任务结束执行[维护检查](maintenance.md)和 `scripts/clean.ps1`，报告删除/保留、测试边界及最终 Git 状态。

## 专题入口

[架构](architecture.md) · [编码](coding-standards.md) · [UI](ui-design.md) · [动画](animation-spec.md) ·
[Zotero](zotero-integration.md) · [测试](testing.md) · [维护](maintenance.md) · [版本演进](versioning.md)

[GitHub 仓库准备](github.md)

[首版能力与扩展起点](../releases/v1.0.0.md) · [逐版本说明](../releases/README.md) · [构建发布](../../releases/README.md) · [验证报告](../reports/README.md)

[返回文档总导航](../README.md) · [返回项目首页](../../README.md)
