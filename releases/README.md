# 构建、归档与 GitHub Release

含 Paper Cards 的安装包见 [1.1.0 说明](../docs/releases/v1.1.0.md)。首版完整交付归档到 releases/v1.0.0；
dist 是构建暂存输出，build 是编译与验证工作区。
这些暂存目录在归档核验后可清理，按需重建；build/tools 中的本地编译器保留复用。
本地归档与 GitHub Release 分别管理。

## 构建

```powershell
.\scripts\dev-setup.ps1
.\scripts\build.ps1 -IsccPath 'C:\path\to\ISCC.exe'
```

默认门禁执行 Ruff、完整 pytest、文档/发布树检查及 pip check，再运行 PyInstaller、许可打包、Inno Setup 与封装自检。
测试使用唯一 basetemp，旧测试现场不自动覆盖。门禁失败停止；SkipTests 仅供已有记录的候选封装，不作为正式验收的替代。
版本来自 __version__，ISS 独立默认值保持一致。源图重建工具是 scripts/make_icon.py。

PyInstaller 采用 one-directory，运行树为 build/release/ZoteroFileExplorer，动态 Qt DLL 保留可替换性。
运行资源只收集 app.ico 和 app.png；不收集本地设计候选、用户文献、索引或开发环境。
verify_package.py 在 System32-only PATH、移除 Python 环境变量后验证打包 EXE。

安装验收使用同一 ISS/payload 的独立 AcceptanceTest AppId，输出到项目内绝对路径 build/acceptance-installer，
再运行 scripts/test_installer.py。它验证未勾选桌面时不新建、同名外部快捷方式保留、勾选创建、旧默认图标快捷方式在未勾选重装时更新，
以及开始菜单图标、自检、EXE 哈希、卸载及数据保留；不等同全面生产覆盖升级。

安装器将 ICO 的 SHA-256 写入独立图标文件名，桌面、开始菜单和卸载入口显式引用该文件。
图标内容变化会改变 Shell 缓存键；安装后仅通知相关快捷方式更新，不删除全局缓存或重启 Explorer。

## 首版归档内容

```text
releases/v1.0.0/
  ZoteroFileExplorer-1.0.0-Setup-x64.exe
  app/ZoteroFileExplorer/             可直接运行的完整目录
  source/                            项目源码 ZIP 与逐文件清单
  ThirdPartySources/                 Qt/PySide 对应源码和 manifest
  README.md                          交付说明
  SHA256SUMS.txt                      归档文件校验
```

安装器、DLL、源码 ZIP 与对应第三方源包均为本地/GitHub Release 资产，不进入普通代码仓库。
每版本 README/校验元数据可跟踪；源码导出排除每版本生成校验文件，避免哈希循环。
archive_delivery.py 先按审查清单生成并逐文件校验 dist/source，再为 dist 交付生成 SHA-256。
组装交付前，将本版 releases/v1.0.0/ThirdPartySources 复制到 dist/ThirdPartySources，或运行 scripts/fetch_license_sources.py 准备精确对应源包。
归档后逐文件核对副本与源；GitHub Release 应绑定实际公开提交，上传相同校验的资产。

## 维护与后续发布

按[版本规则](../docs/development/versioning.md)维护后续增量。
仅在用户明确要求或证明替代关系后清理旧交付；先落盘清单、检查绝对边界、reparse point、硬链接、占用与哈希，再逐文件操作。
第三方对应源码及 notices 随交付保留。每次任务结束执行[维护清单](../docs/development/maintenance.md)。
版本说明和已知限制见[1.0.0](../docs/releases/v1.0.0.md)和[1.1.0](../docs/releases/v1.1.0.md)。

[文档导航](../docs/README.md) · [开发手册](../docs/development/README.md) · [GitHub 准备](../docs/development/github.md)
