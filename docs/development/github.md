# GitHub 公开源码

## 公开范围

仓库包括 src、tests、assets 正式图标、config、installer、scripts、licenses、docs、社区说明与 .github。
保留 Python/Qt Widgets 分层，不建立空模板目录。
.venv、build、dist、work、backups、缓存、用户附件与运行数据不进入公开树。
正式图标源图是 assets/icons/app-source.png，安装包只收集 app.ico 和 app.png。

## 首次上传

1. 运行 scripts/check_repository.py 和 scripts/check_docs.py，核对图标来源、许可证、截图、署名和配置。
2. 审查 main 中的公开源码，确认 v1.0.0 标签与交付版本对应。
3. 在目标账号/组织创建空仓库，明确公开可见性；配置 origin，推送 main 与明确选择的标签。
4. 首次推送后检查 Windows CI 实际结果，配置默认分支保护和私密漏洞报告入口。
5. 在 GitHub Release 上传本地 releases/v1.0.0 内的安装器、校验与对应第三方源码；可运行目录可打包后作为资产提供。

没有配置仓库地址前，不生成虚构下载链接或声称已上传。当前脚本只检查本地树，不进行完整凭据审计。
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
