# 编码与 Git 规范

Python 3.11–3.14；模块/函数使用 snake_case，类使用 PascalCase，Ruff 配置是格式和静态规则来源。
保留 src 包及分层，不为目录整齐改变 API 或拆出无人使用的模块。若验证后引入 QML，组件使用 PascalCase；当前没有应用 QML。

网络、文件验证、索引查询放 worker；Qt 对象只在 GUI 线程更新，合并过时搜索。
身份必须包含 instance/library/item，不能按 item key 独立识别跨库记录。
动画只通过集中 tokens/policy；依赖最小化，变更依赖时同步 pyproject 与开发锁。

## Git 和文档

- 先检查 `git status --short`；保留已有用户修改。结构调整前建立限定范围 checkpoint，不盲目提交全部未知文件。
- 新分支默认 `codex/`；没有用户要求时不推送或创建远程发布。
- 源码、夹具、正式资源、安装定义、脚本、文档与 CI 进入版本管理。
- `.gitignore` 管理本地环境、缓存、构建、备份与发布二进制；忽略不等于允许删除。
- 一个主题一个权威正文；其他文档使用 GitHub 相对链接。专题页提供返回开发首页、文档总导航链接。
- 检查链接及本地锚点；文件改名同步所有引用，不复制不正确的相对路径。
- 版本采用 MAJOR.MINOR.PATCH；源码版本源为 `__init__.__version__`，ISS 独立默认值保持一致。
- 变更和记录同步，未发布内容记 Unreleased；版本日期、测试数、Tag/Release 链接必须有证据。

测试命令见[测试规范](testing.md)，任务结束清单见[维护规范](maintenance.md)。

[返回开发文档首页](README.md) · [返回文档总导航](../README.md)
