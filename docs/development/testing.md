# 测试流程与验收边界

## 必需检查

从仓库根目录执行，顺序为 Ruff、完整 pytest，再检查文档：

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/check_docs.py
```

也可运行 `.\scripts\test.ps1`，会汇总各检查退出码，即使测试失败仍执行文档检查，并返回失败。
CI 在 Windows runner 上执行检查；托管 runner 明确排除需要交互桌面的 Shell 接收端测试，不等同完整本地验收。
CI 在 pytest 前显式创建 `build`：全新检出不包含这个被忽略的目录，
而配置中的 `--basetemp=build/pytest` 要求其父目录已存在。首次本地运行上述命令前也需创建 `build`。
窗口布局往返测试按当前可用屏幕选择尺寸，保留尺寸精确恢复、列布局和选择状态断言；
避免固定大窗口触发 Qt 的屏幕边界修正而在较小的托管虚拟屏幕上误报。

## 覆盖范围

- unit：分类、索引、恢复逻辑、工程清理边界与文档检查器。
- integration：模拟 Local API、同步、Qt 视图、原生剪贴板、MIME、响应性与 motion。
- 清理安全回归：默认预览、未知/跟踪文件保留、路径穿越、父级/嵌套 junction、硬链接、清理前内容变更、清单先落盘。
- 视图变更必须验证多选、跨实例/库同 Key、QMimeData 本地 URL、CF_HDROP、QDrag CopyAction。
- QML 加载：目前无应用 QML，spec 明确排除 QtQml/QtQuick，因此不适用；不得报告为 QML 加载通过。

## 资源、打包与真实桌面

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m zotero_file_explorer --data-dir build/dev-smoke --no-sync --smoke-test
.\scripts\build.ps1
```

构建/安装验证见[发布流程](../../releases/README.md)。源码自检不替代封装 EXE 自检、安装/卸载或覆盖升级。
安装回归通过独立 AppId 和带 Acceptance Test 后缀的桌面/开始菜单快捷方式隔离正式安装。
需覆盖桌面选项关闭、同名外部快捷方式、勾选创建，以及遗留默认 EXE 图标在关闭选项重装时迁移；核对实际 .lnk 的目标和图标哈希，并验证卸载。
Shell 接收端探针在 DragEnter/DragOver 中传递 MK_LBUTTON | MK_CONTROL，Drop 时释放左键并保留 Ctrl。
探针保持 20 秒超时，验证实时 Qt 和固化剪贴板两种路径；按下和释放状态必须与实际拖放一致。
测试继续核对目标文件内容和源文件哈希；详见[本版验证](../reports/validation-v1.0.0.md)。每轮仍需报告实际通过/失败/未执行。
跨应用鼠标拖放、Shift 拖动、多文件、中文/空格路径、取消行为与源文件哈希需在交互 Windows 中另验。
本版实际结果见[验证报告](../reports/validation-v1.0.0.md)，后续结果维护于[报告索引](../reports/README.md)。

## 人工拖放验收

1. 使用公开的独立测试附件和空目标目录，记录源文件大小、SHA-256；不操作真实 Zotero 原件。
2. 主窗口拖文献行、展开子行到 Explorer/桌面，检查目标为真实文件，源文件哈希不变。
3. 多选、重复路径、Shift 拖动分别验证；再测试 Ctrl+C / Ctrl+V 和快捷窗口，确认只复制。
4. 用中文、空格、#、% 文件名重复；只移动测试源验证缺失路径不传递，取消拖动不产生文件。
5. Chrome/Edge、本地上传页面及需要支持的聊天客户端逐项记录版本、权限、接收状态；不发送测试文件或用户文献。
6. 单独记录热键冲突、开机启动、主题切换、多 DPI、长时间运行和生产覆盖安装，不用自动测试代替实机结论。

## 性能与证据

使用 `scripts/benchmark.py --output build/performance-current.json` 和 `scripts/benchmark_ui.py`。
交互回执可单独运行 `scripts/benchmark_feedback.py --data-dir build/feedback-new-run --output work/feedback-new-run.json`；
数据目录和报告必须是新路径，拒绝覆盖。工具仅创建合成库，报告区分模型填充、CPU paint、事件循环和动画对象数。
模拟 500 / 5,000 / 20,000 篇；区分模型填充、CPU paint、事件循环和 compositor/display FPS。
不要覆盖历史结果；原始运行输出优先写 build，审查隐私后才将必要汇总放 docs/evidence。
不更改用户 Zotero 库；live_probe 只读，修改型场景由模拟服务提供。

[返回开发文档首页](README.md) · [返回文档总导航](../README.md)
