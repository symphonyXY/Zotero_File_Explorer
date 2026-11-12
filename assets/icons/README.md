# 应用图标

`app-source.png` 是项目所有者选定的 AI 生成“06-fusion-minimal”原图，作为 1.0.0 应用标识，按项目 MIT 许可证提供。
它不是 Zotero 官方标志，不表示官方合作或背书。

- `app-source.png`：保留原始像素与透明度的正式源图。
- `app.png`：512 × 512 的界面与 README 展示资源。
- `app.ico`：16、24、32、48、64、128、256 像素的 Windows 图标。

重新生成：`.venv/Scripts/python.exe scripts/make_icon.py`。过程只缩放和居中，保留图形及 alpha；不会删除输入文件。
输出哈希和 Qt 加载记录见[图标证据](../../docs/evidence/icon.json)。

[返回 UI 规范](../../docs/development/ui-design.md) · [返回项目首页](../../README.md)
