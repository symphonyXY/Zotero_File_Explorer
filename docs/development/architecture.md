# 架构与数据保护

## 数据流

`只读 Local API → Record/Library → SyncService → 本软件 SQLite → 后台搜索 → MainWindow / QuickWindow → Qt 原生文件接口`

API、同步一致性、实例身份与附件分类的详细约束见 [Zotero 集成](zotero-integration.md)。

`storage/index.py` 保存最少元数据和派生搜索字段。原始记录用于增量合并，documents 为界面检索投影。`overrides.json` 单独保存手动分类、主附件和路径映射，重建索引保留它。SQLite 损坏时把损坏库及 WAL/SHM 改为带时间戳文件，建立新库，保留诊断线索。无法读出的 overrides 禁止静默覆盖。

## 搜索与界面

SQLite 参数化查询，按库、年份建立索引。NFKD/casefold 去重音归一化；多词采用 AND 子串匹配，支持中文、英文、引号短语和标点。没有 PDF 正文或编辑距离搜索。分类、标签使用 JSON exact membership，防止相似 Key 误命中。文件类型匹配任意已确认原件；默认操作始终使用稳定选定的主附件，具体子附件可展开选择。

界面查询在 QThreadPool 执行，180 ms 防抖、过期结果丢弃。标准窗口每页 500，前后翻页可遍历全库；快捷窗口最多 200 条，适合输入关键词收窄。主线程只填充当前页；不加载 PDF 内容。两窗口共用索引和配置。主题通过 Qt 系统颜色变化信号跟随，并允许强制浅色/深色。双语由集中 catalog 管理。

## Windows 文件集成

### 视图与动画边界

`ui/paper_model.py` 提供只读树模型，每个文献/附件节点存一份共享数据；列值按 Qt 角色读取，
不再创建九份 QStandardItem。`ui/paper_view.py` 负责选择、当前行、滚动和展开状态恢复。
`ui/motion.py` 集中管理 Widgets 动画，Windows 系统偏好由 `platform/windows.py` 只读获取。
用户设置向后兼容；旧配置缺少 motion/animation_speed 时采用默认值。详细规则见[动画规范](animation-spec.md)。

QMimeData.setUrls(QUrl.fromLocalFile(...)) 交给 Qt 的 Windows MIME 转换器输出 CF_HDROP。QDrag.exec 只允许 CopyAction，另设置 Preferred DropEffect=1。Ctrl+C 使用同一个文件 MIME 构造器；路径、名称复制为不同菜单。操作前重新检查文件存在、可读、去重；无效文件不传递。没有临时 PDF、快捷方式、虚拟 URL 或文字路径冒充拖拽。

全局热键使用 RegisterHotKey/MOD_NOREPEAT 和原生事件过滤器；注册冲突明确提示。QLocalServer + QLockFile 实现单实例并可唤醒主/快捷窗口。用户主动保存开机启动选项时才写 HKCU Run。本软件退出时注销热键、隐藏托盘、停止轮询、取消同步，等待有限时网络请求完成后退出 GUI。

## 风险与边界

- 网络磁盘的操作系统 I/O 可能长时间等待；索引检查在后台，明确的文件操作仍可能受网络延迟影响。
- 完整 Key 清单是 O(N)，元数据增量提交目前重建本地派生投影；2 万篇的后台测量见性能报告。
- 未提供跨数据库手动合并或离线分区选择界面，离线展示最近一次成功提交的实例。
- 不支持扫描 Zotero 原始数据库、全文搜索、文件移动、云端同步或 PDF 翻译。
- Qt 文件数据层与 Shell/目标应用的交互验收分别记录，避免把实现当作全目标认证。


[返回开发文档首页](README.md) · [返回文档总导航](../README.md)
