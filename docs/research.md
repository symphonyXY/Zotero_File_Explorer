# 当前实现的技术依据

协议与分类实现参考的上游快照、源码链接和已有文件哈希见[来源记录](evidence/research-sources.json)。这些项目是接口或设计参考，不作为本程序实现代码捆绑。

## Zotero Local API

依据 [Local API 文档](https://www.zotero.org/support/dev/web_api/v3/local_api)和 [Zotero 源码](https://github.com/zotero/zotero)中的本机 API、附件与条目实现，只使用 GET 端点读取元数据和真实文件 URL。
实例、文献库和条目共同构成身份；通过版本清单及提交前复核维持同步一致性。没有实例标识的兼容模式采用完整读取，能力边界见[集成规范](development/zotero-integration.md)。
程序不打开 Zotero 原始数据库。

## 翻译附件分类

[Zotero PDF2zh](https://github.com/guaguastandup/zotero-pdf2zh)各代实现的文件名约定用于识别产物后缀。
文件名与附件标题分别保存；点分隔翻译后缀、mono/dual 布局及 compare/cut 加工后缀按完整终端结构识别。
歧义后缀需要同父原件或标题佐证，不充分时进入待确认；不凭父子关系或随机前缀直接隐藏附件。
分类规则和覆盖设置属于本应用，不读取插件私有设置，也不调用翻译服务。

## 文件与桌面接口

[Qt 拖放文档](https://doc.qt.io/qtforpython-6/overviews/qtgui-dnd.html)和 [Microsoft Shell 剪贴板文档](https://learn.microsoft.com/en-us/windows/win32/shell/clipboard)是 QDrag、QMimeData、本地 URL、CF_HDROP 与 CopyAction 的接口依据。
PyZotero、ZotMoov、windrop 和 Qt 示例仅用于接口与设计比较，未捆绑其程序或复制其实现。
安装器使用 Inno Setup，保留其简体中文消息文件归属。

## 再分发材料

实际运行依赖、许可及对应源码以[第三方说明](../THIRD_PARTY_NOTICES.md)、licenses 和[第三方源包清单](evidence/third-party-sources.json)为准。
源码参考项目的版本号属于上游快照，不是本程序的历史发行版本。

[返回文档导航](README.md) · [开发手册](development/README.md)
