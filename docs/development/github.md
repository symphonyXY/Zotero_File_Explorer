# GitHub 公开源码

## 公开范围

公开仓库为 [symphonyXY/Zotero_File_Explorer](https://github.com/symphonyXY/Zotero_File_Explorer)，默认分支为 main。
仓库包括 src、tests、assets 正式图标、config、installer、scripts、licenses、docs、社区说明与 .github。
保留 Python/Qt Widgets 分层，不建立空模板目录。
.venv、build、dist、work、backups、缓存、用户附件与运行数据不进入公开树。
正式图标源图是 assets/icons/app-source.png，安装包只收集 app.ico 和 app.png。

## 推送与发布

1. 运行 scripts/check_repository.py 和 scripts/check_docs.py，核对图标来源、许可证、截图、署名和配置。
2. 审查待提交的公开源码、许可证与版本说明，确认 origin 和远端分支。
3. 推送源码后检查 Windows CI。发布二进制时，按发布流程将安装器、校验文件和对应源码作为 GitHub Release 附件上传，并将标签绑定到构建版本对应的提交。

下载链接以实际发布的附件为准。公开前还需检查个人路径、凭据和用户数据。
文件导出包含未忽略的新文件并尊重删除；源码 ZIP 不带 .git 或本地工作记录。
每版本的生成校验文件不再放回源码 ZIP，避免归档对自己的哈希形成循环。

## 检查命令

```powershell
.\.venv\Scripts\python.exe scripts/check_repository.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git status --short
git diff --check
git ls-files -ci --exclude-standard
```

[返回开发手册](README.md) · [发布流程](../../releases/README.md) · [贡献指南](../../CONTRIBUTING.md)
