# Zotero 集成

`api/client.py` 固定使用 GET，只允许回环 HTTP /api 地址，禁用代理和自动重定向；协商 API v3，校验 Zotero-Server-ID。分页固定 100，版本不一致拒绝提交。403、404、412、501、断线分开处理，不会申请写权限。

`services/sync.py` 先读库与完整 Key/版本清单，再读 since 变更（只有 Server ID 存在时），恢复父子与分类关系，解析真实附件路径，完成一致性检查后统一事务提交。失败保留上一次索引。群组变化按每次发现结果同步，Key 唯一标识为 `(instance, library, key)`。无 Server ID 的旧版总是完整获取，不能保证同一路径替换数据库后的身份检测，需手动重建。

`core/classification.py` 是独立可测试的保守识别器。手动确认优先，其次用户通配符规则，再使用经过源码核实的产物结构和同父附件证据。不支持的类型不会误入主列表。Original 是“按当前规则确认原件”，不对未知插件或人为完全改名的翻译件作无法证明的保证；可随时纠错。记录原因，不删除文件。


## 数据与线程边界

浏览和索引只读本机 API 与已有附件。速览卡写入走独立的本机授权接口。禁止直接打开/写入 Zotero 原始数据库，禁止移动、删除原件或复制整套附件库。
网络、磁盘验证、索引查询在 worker 中执行；Qt 对象与文件 MIME 构造在 GUI 线程完成。
运行数据默认在 `%LOCALAPPDATA%\ZoteroFileExplorer`；测试必须显式指定项目内隔离目录。
常规真实 API 探测仅 GET；新增、删除、同 Key 跨库和实例切换的回归测试使用模拟服务。Paper Cards 的独立写入验收见下节。

## Paper Cards 服务和编辑界面

`core/paper_cards.py` 定义模板与标识。`services/paper_cards.py` 使用实例标识、个人库、父条目 key 和子附件 key 校验目标。
优先识别带专用标签的存储型 Markdown。对于同名的旧卡片，读取文件头核对类型与格式版本；第一次编辑这类卡片时补充识别标签。
创建前校验文献库版本，分步上传使用同一个附件 key，中断后可以重试。
`services/card_transfer.py` 复用第一阶段已验证的上传协议，在提交前重新读取附件状态与旧文件 MD5。
只有回读的正文与待保存内容一致，界面才显示已保存。写入服务限定于本机 Zotero，云端状态由 Zotero 管理。

`storage/card_drafts.py` 在单独的写入线程按顺序原子替换草稿，文件名按实例、库和父条目计算。
`ui/paper_card.py` 负责详情页、Markdown 编辑预览、显隐式复习与冲突对照。
可从 `card_template` 扩展模板，单独扩展复习数据；当前版本采用手动复习。预览使用 Qt 内置 Markdown，不提供数学公式排版。

## Paper Cards 第一阶段验收

本机 Zotero 10.0.8 返回 Local API v3 和实例标识，个人库已选择 WebDAV。该版本的
`GET /api/items/new?itemType=attachment&linkMode=imported_file` 实测返回 404。验收脚本直接提交附件字段。
Explorer 使用现有客户端读取数据，并通过独立速览卡服务提交授权写入。协议依据见
[本地 API](https://www.zotero.org/support/dev/web_api/v3/local_api)、
[对象写入](https://www.zotero.org/support/dev/web_api/v3/write_requests)和
[文件上传](https://www.zotero.org/support/dev/web_api/v3/file_upload)。

在配置了测试所用个人库的设备 A，从项目根目录运行以下命令。保存输出的 UUID，用于中断后重试和第二台设备核对。

```powershell
$cardRun = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe scripts/probe_paper_cards.py write-test $cardRun
```

脚本在 Zotero 官方对话框申请写入授权。个人库下的合成文献标题为 `Paper Cards test <UUID>`，
其子附件为 `PaperCard.md`。脚本通过父子 key、类型、存储模式和验收标签核对身份。
使用相同 UUID 重试会复用这些条目。写入密钥仅存在进程内存中。单次授权可能需要确认多次。

1. 初次写入使用 `If-None-Match: *`。Zotero 给出本机上传地址，脚本发送 UTF-8 字节并向文件端点登记上传。
2. 使用 `/file/view/url` 返回的文件地址只读核对正文，使用初版 MD5 和 `If-Match` 更新同一个附件。
3. 再次使用旧 MD5 请求上传授权，预期收到 412。复查父子关系和正文。此项测试覆盖本机 API 的文件前置条件。
4. 在设备 A 的 Zotero 执行同步，并在使用同一账号和 WebDAV 配置的接收端同步。接收端可使用设备 B，
   或在同一台电脑新建独立 Zotero 配置，指定空数据目录，将个人库附件下载设为“按需”。找到相同标题的文献，
   从 Zotero 下载并打开附件，核对 UUID 及末行“第二版：已编辑。”。有开发环境时，在 B 运行
   `scripts/probe_paper_cards.py verify <同一UUID>`，它以只读方式核对附件 key 和完整正文 SHA-256。
5. 记录接收端的配置、下载前附件是否存在以及下载后的 SHA-256。同机独立配置用于验收文件传输，跨物理设备兼容性另记。

2026-11-18 在同一台 Windows 电脑的两个独立 Zotero 10.0.8 配置上验证了个人库附件的创建、更新和按需下载。
旧 MD5 的写入被拒绝。接收端下载的 Markdown 与发送端和 Koofr 下载件逐字节一致。跨物理设备兼容性尚待验证。

本次验收使用的合成条目及其附件已通过 Zotero 删除。编辑器在写入和登记上传时检查磁盘正文，可以发现外部编辑器尚未同步的修改。
同一文献出现多个候选时需确认目标附件，候选集合再次变化会重新询问。群组库文件同步范围见
[Zotero 文件同步说明](https://www.zotero.org/support/sync)。

实际兼容验收见[测试规范](testing.md)及[版本说明](../releases/README.md)。

[返回开发文档首页](README.md) · [返回文档总导航](../README.md)
