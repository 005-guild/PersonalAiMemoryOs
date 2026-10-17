> 历史文档快照：归档于 2026-10-17，保留 0.6.6 及此前的发布、验收和使用记录。
>
> 日常操作与当前配置请以 [完整中文使用手册](../readme-cn.md)、[RAG 配置指南](rag-guide-cn.md) 和 [完整配置参考](config-reference-cn.md) 为准。以下路径、运行状态和验收结果属于记录时点，不表示当前程序或个人数据库的实时状态。

# Personal AI Memory OS — 中文使用说明

[English README](../README.md)

一个在本机运行的个人知识管理系统，将原始资料整理成可编辑的知识笔记，并支持语义检索和带引用的问答。

当前源码版本 **0.6.6**，数据库迁移版本 **0004**。现有 Docker 服务保持 **0.6.0** 原部署，桌面版使用独立数据。

**资料导入 → 浏览编辑 → AI 生成草稿 → 人工采纳 → Markdown 笔记 → 检索与引用问答**

AI 和 RAG 默认关闭。无需配置模型，也能使用资料管理、离线导入、笔记编辑和 Markdown 双向同步。真实 DeepSeek、Embedding 检索效果和问答质量仍待单独验收。

## Windows 便携桌面版

解压 `PersonalAiMemoryOs-0.6.6-windows-x64.zip` 到可写目录，双击 `PersonalAiMemoryOs-0.6.6/` 中的 `PersonalAiMemoryOs.exe`。系统 WebView2 提供独立桌面窗口；基础管理不需要 Python、uv 或 Docker。保留整个目录，包括 `_internal`，不能只复制 EXE。系统需有 Microsoft Edge WebView2 Runtime 和 .NET Framework 4.8；缺少时按启动提示前往微软官网下载，程序不会自动安装。

**0.6.6 可视化 AI 设置**：左上品牌下方新增“设置”，桌面菜单和窄屏顶部也可直接进入。可修改文本生成 AI 开关、默认模型和多套模型配置，包括接口协议、地址、模型、鉴权、输出限额及高级 JSON 参数。页面只读展示实际运行目录、数据目录、数据库文件、知识目录、配置目录和 `.env` 位置，不修改业务数据路径，也不编辑或开启 Embedding / RAG。数据库仍为 `0004`，需使用完整新版程序。

**保存与密钥**：保存只写入下次启动配置，不调用模型、不热加载、不自动重启；需完全退出后重新打开。密码框始终从空值开始，留空保留已有密钥，新值影响所有共用该引用的模型配置。已有密钥只显示“已配置”，不会回传或保存在浏览器存储、YAML、数据库及报告中；本机 `.env` 保存明文凭据，请将它和整目录备份作为个人配置保管。环境变量托管的值不能在网页中覆盖；Docker 页面为只读，仍需修改宿主机配置后显式重建服务。

**0.6.6 工程验收通过**：全量测试 **925 项通过、3 项 Windows 符号链接权限跳过、1 条已有 Starlette／HTTPX 警告**，耗时 52.81 秒（`.cache/v066/pytest-final.log`）；30 个 JavaScript 模块语法和 47 包锁文件检查通过。六组受控 Chromium 已通过四协议完整字段／高级参数往返、密钥保护、版本冲突、只读、未保存离开、过期响应及 1440／390 布局。真实隔离本机 API＋浏览器已验证保存后不立即生效、重启后加载模型和密钥，端点请求和真实模型调用均为零。报告为 `.cache/settings-ui/3e237a1470ec44ddabadbcfef1abf23c/report.json`、`.cache/settings-local-real/971c3d69449c4822aec2c418f4cf61d0/report.json`。下列四套实际冻结 EXE 流程也已通过；本轮不重部署正式 Docker，不改变原真实模型质量验收状态。

0.6.6 独立发行目录为 `dist/PersonalAiMemoryOs-0.6.6/`，ZIP 为 21,989,284 字节。EXE SHA-256：`0899b2b7355f9be23946e30d1258b50839616b448623798daaa93f9ce1ce1b0b`；ZIP：`d05d5c512b5b07dff3cc20adfc2dc24f4184ae491dc096ff8a9ba4dd9870ab8e`。`.cache/v066/final-audit.json` 已核对源码指纹、36 个网页资源、235 个发行文件、x64 GUI、ZIP 完整性及空净发行目录，15 个旧发行文件和正式库哈希未变。已有安装和现用资料没有被覆盖或复制到新包。本版无迁移；将原来已有的间接依赖 `python-dotenv` 显式列为直接依赖，没有新增实际安装包、模型 SDK 或框架。

实际冻结 EXE 的设置验收已通过：保存一次且不立即生效，真正退出重启后加载模型和密钥，密码无 DOM／浏览器存储回显，原配置及业务行哈希保留，成功写入后的凭据恢复文件已清理，模型端点请求为零。报告 `.cache/ai-settings-validation/cc980ee5477944138fdbc946a39a2d5d/report.json`。同标题阅读回归通过（`.cache/source-groups-validation/c58681190c554d5bb5adec40be7aee09/report.json`）；排序在 27 组／67 篇资料中通过八种顺序及跨页检查，资料快照未变（`.cache/source-sorting-validation/1079db283786450d9851dfd4a9b9523c/report.json`）。完整桌面回归通过 17 项流程、在途模拟调用正常完成并保留草稿且未创建笔记、非法配置中文原生提示（`.cache/desktop-validation/2042177c88c04b149202973303f02499/report.json`）。以上均实际使用本机 WebView2，真实模型调用为零、正式哈希未变；真实质量、生产原生另存为交互及第二台电脑实测仍保留单独验收边界。

最终清理报告 `.cache/desktop-066-cleanup.json` 确认自有桌面进程为零，四个验收端口均已释放。发行目录仍为空净的 235 个文件／解包 43,552,764 字节，旧发行文件及正式库最终哈希仍一致。

**0.6.5 资料库排序**：可按“标题／资料数量／来源类型／更新时间”升序或降序排列，也可点击列标题切换。排序作用于整个筛选结果后再分页；切换排序回到第一页，翻页、筛选、刷新和进入详情后返回会保留排序。默认“更新时间降序”，即最近更新在前。标题和类型按数据库字符顺序排列，不是中文拼音；同标题包含多种来源类型时，以当前可见记录中字符顺序最前的类型为排序依据。仍为数据库 `0004`，需升级完整程序。

**0.6.5 验收通过**：856 项测试通过、3 项 Windows 符号链接权限用例跳过、1 条已有警告（55.80 秒），26 个 JavaScript 模块检查通过。浏览器核对了八种排序、跨页、表头键盘操作、排序控件焦点、筛选／详情返回及 1440／390 布局。真实 EXE 在 27 个标题／67 篇独立资料中验证了八种排序与翻页、类型筛选、返回上下文和重启，排序前后的资料快照一致。原 571 篇语料的隔离缓存副本也通过八种排序共 176 页检查，432 个标题组无遗漏或重复，全部表数据和文件哈希未变；没有调用真实模型或修改正式资料。

报告：浏览器 `.cache/source-sort-ui/84cc445457824fdeb9ab7d9181b811ac/report.json`；真实 EXE 排序 `.cache/source-sorting-validation/4711e8bc33764bdeaa9626dd19a33d50/report.json`；原分组流程 `.cache/source-groups-validation/e99a0e13f9164815a627344e472a42a6/report.json`；571 篇缓存排序 `.cache/source-sort-corpus/6d5e615811744ad4b312bc678762d6da/report.json`；完整桌面回归 `.cache/desktop-validation/6a4b97d0b5ed460b94187fa9f5decd13/report.json`。首次并行完整回归因窗口提前正常退出而未完成，失败报告 `4495fafaad554a42964b720f5c84d091` 保留，关闭原因未确定；单独重跑已通过 17 项桌面流程、在途模拟调用正常退出和非法配置检查。

历史 0.6.5 完整包位于 `dist/PersonalAiMemoryOs-0.6.5/`，ZIP 约 21 MiB。EXE SHA-256：`eb03ee7fe789564f9e49769ba819ec495ced8480146c32016517985815a990be`；ZIP：`4a93068766ea3a33b7bce80cc90aeb99f5fe8076d9d13e1076eb6b08448b8bd1`。审计 `.cache/v065/final-audit.json` 确认源码／资源一致、ZIP 完整、发行目录不含个人数据，12 个旧发行文件和正式库哈希未变。当时使用过的安装目录未覆盖，新包没有复制现用资料；升级前按下方说明退出并备份、保留配套配置及数据。正式 Docker 仍保持 0.6.0。

**0.6.4 资料库分页与同标题阅读**：资料库按完全相同的标题显示一项，并标明该标题下有几篇资料。可选每页 20／50／100 个标题、点击页码或输入页码跳转；筛选后重新从第一页开始。点进标题后，分别展示各篇的作者、类型、原文链接和 Markdown 正文，可独立编辑、生成草稿或查看关联笔记。组内可按每页 5／10／20 篇翻页；返回列表或编辑后返回时保留原筛选和页码。同标题仅在界面分组，不合并、覆盖或删除原始资料；修改某篇标题后，它会按新标题归组。本版包含新后端接口，升级需使用完整程序，数据库仍为 `0004`。

**0.6.4 验证结果**：809 项测试通过、3 项 Windows 符号链接用例跳过、1 条已有警告（39.39 秒），25 个 JavaScript 模块检查通过。五组受控浏览器验证覆盖页码、搜索焦点、长正文和安全预览、版本冲突、恢复及快速切页竞态。真实本机与打包后的 EXE 均通过 48 篇资料／46 个标题的分页、跳页、三作者完整原文、编辑返回及独立存储检查，EXE 退出重开后仍保留。

另外只读使用原始文件，在 `.cache` 空库中验证了 **571 篇 → 432 个标题组**，71 个标题有多篇内容、最多 12 篇；22 页遍历及 571 篇正文哈希均一致。原始 1,898 个文件没有修改，未新增知识笔记或调用真实模型。报告：`.cache/source-group-corpus/82da5e247698417e92588e8ee20168fc/report.json`；真实 EXE 分组验收：`.cache/source-groups-validation/44988b71a4bc426ba5719850074a72a6/report.json`；本机浏览器：`.cache/source-groups-local/28c6165e81e74d1d8bbce882eff17699/report.json`；受控浏览器：`.cache/source-groups-ui/cc06ede91d474cfcbe004eed8b56cd88/report.json`。

历史 0.6.4 交付时，新目录 `dist/PersonalAiMemoryOs-0.6.4/` 保持首次运行的空库状态，ZIP 约 21 MiB。EXE SHA-256：`02851318327a7424bf8b2d6b261fd5f396fea8d381b4dd9b91ae2fe6e57b04b0`；ZIP SHA-256：`6d5a5182b8d56b10003cd7137dcc3969d697fd5fbb125a89cbfc8f46284aa412`。发行审计 `.cache/v064/final-audit.json` 核验了资源、源码指纹、x64 GUI、ZIP 完整性及正式库与 12 个旧二进制／归档／校验文件未变。当时使用的 0.6.3 程序未替换；每次升级均需退出、备份并保留已有资料。

完整 EXE 回归同样通过：17 项桌面流程、在途模拟调用正常完成后退出、非法配置原生提示、重启、整体移动及端口释放。报告 `.cache/desktop-validation/7838f4117cb941aebe5f68addf6b9aeb/report.json`；回归资料均在 `.cache`，结束后只保留原有用户程序运行。生产模式原生“另存为”、第二台电脑及真实模型质量仍按后文保留为单独核查项。

**0.6.3 知乎文件夹导入**：打开“资料导入”，切换到“知乎 Markdown 文件夹”，选择导出目录，先预演，再提交；支持回答、文章和想法。每次最多 1,000 篇／请求体 10 MiB，自动跳过 README 目录索引、进度 JSON 和图片。只建立原始资料，不调用模型或自动建立知识笔记；导入后到“资料库”检查。

**0.6.2 界面改进**：知识笔记列表可勾选单篇或全选当前页，再点击“批量删除”。确认后移入回收站，可恢复；切换筛选或翻页会清空选择，回收站中的笔记不能再次勾选删除。操作逐篇校验读取时的版本，部分失败会展示原因；连接中断或服务故障会停止后续提交，不自动重试。搜索与问答中的“检索数量”已改为横排，与左侧标签对齐，窄屏自动换行。

**已有便携版升级**：不要覆盖含有个人数据的旧目录。先正常退出旧程序并备份完整目录，再把旧版的 `.env`、`config/`、`data/` 和完整 `knowledge/`（含隐藏标记文件）复制到尚未运行的新版目录，再启动新版。自定义过数据路径时，也需一起保留对应的目录内文件。新版不会自动读取其他便携目录的数据。

首次启动创建空库，AI/RAG 默认关闭。`.env`、个人模型配置、`data/memory.db`、`knowledge/`、日志和浏览器缓存均在 EXE 所在目录中，不使用当前工作目录，也不读取项目或 Docker 的正式资料。后端使用随机空闲的本机端口，不占用 18000；同一目录重复双击会唤起已有窗口。

菜单可打开 AI 接口设置、数据、配置和日志目录。设置中保存、或手动修改模型 YAML／`.env` 后，都需完全退出并重新打开桌面版。外部模型和 Qdrant 仍需单独配置，便携包不包含模型或 Qdrant。不要把正式库绝对路径填入桌面配置；桌面运行数据必须位于便携目录内。

关闭窗口时会提示未保存内容；确认后等待同步和在途调用完成，再退出。等待超过 150 秒会继续显示状态，不自动强杀。整体移动便携目录前先退出；备份时将数据库和完整 `knowledge/` 一起复制，包括 `.memory-os-vault`。旧库需要升级时，程序先征求确认，备份并核验后再迁移；未知或更高版本数据库会拒绝启动。源码与 Docker 的迁移命令仍按下文显式执行。

桌面发行包尚未数字签名，不含安装器或自动更新。当前验证在本机 Windows x64 进行，未声称在第二台干净电脑上实测。

开发者可重新生成发行包并验证真实 EXE：

```powershell
uv run --no-sync python scripts/build_desktop.py --output-name PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_desktop.py --bundle dist/PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_ui_patch.py
uv run --locked python scripts/verify_markdown_import.py --mode local
uv run --locked python scripts/verify_markdown_import.py --mode desktop --bundle dist/PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_source_groups.py --bundle dist/PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_source_sorting.py --bundle dist/PersonalAiMemoryOs-0.6.6
uv run --locked python scripts/verify_source_sort_ui.py
uv run --locked python scripts/verify_source_group_corpus.py
uv run --locked python scripts/verify_settings_ui.py
uv run --locked python scripts/verify_ai_settings.py --bundle dist/PersonalAiMemoryOs-0.6.6
```

构建脚本使用 `.cache/desktop-build-venv` 内的独立环境和已锁定的 `desktop`、`build` 依赖组。输出目录、ZIP 和 `.zip.sha256` 位于 `dist/`；校验文件包含 ZIP 与 EXE 的 SHA-256。验收复制到 `.cache/desktop-validation/` 下的中文空格路径，连接实际 WebView2 窗口，测试 CRUD、文件导入、报告下载、未保存关闭、重启、整体移动和错误提示；不会改变正式 Docker 服务或调用真实模型。

**0.6.3 验收已通过**：780 项测试通过、3 项 Windows 符号链接权限用例跳过、1 条已有上游警告（31.95 秒），20 个 JavaScript 模块语法检查通过。本机浏览器与打包 EXE 均用实际文件夹验证了“预演 571 篇 → 创建 571 篇 → 重复导入零新增”，包括 522 篇回答、41 篇文章、8 条想法；571 篇正文哈希一致，退出重开后保留。资料导入没有创建知识笔记、知识 Markdown、处理记录或向量记录，没有复制图片或调用真实模型，原始 1,898 个文件及正式数据库哈希未变。

本机验收：`.cache/markdown-import-validation/4aea4976ee0b402baf38cfe22925a693/report.json`；实际 EXE 验收：`.cache/markdown-import-validation/65516bd88a8c4c488351e79a710cf738/report.json`；完整 EXE 回归：`.cache/desktop-validation/1804c35b68284bc4b1d6c009eaba89ed/report.json`。所有实际导入均发生在 `.cache` 隔离数据库；正式资料请在目标工作台自行预演确认后提交。

历史 0.6.3 完整包位于 `dist/PersonalAiMemoryOs-0.6.3/`，ZIP 约 21 MiB。EXE SHA-256：`305c166587a748b3bcd23f1d3c8e5bafc59a449876c786fef2bb82dd36db25b6`；ZIP SHA-256：`15f589aeee973e8bf87922df9a14ad0f220aa4c96c54e4c7f32d6ba741669a69`。该次交付未覆盖旧安装与旧包；有旧资料需要保留时按上面的升级步骤复制配套数据。正式 Docker 保持 0.6.0，未重新部署。

0.6.2 已通过 **710 项测试、3 项 Windows 符号链接权限跳过、1 条已有警告**，18 个 JavaScript 模块语法检查、隔离真实数据库浏览器测试及完整发行 EXE 验收。另在真实 WebView2 窗口中确认：列表选择两篇删除后版本为 v2、未选笔记保持正常及 v1，八组搜索／问答布局通过，退出后数据保留、端口释放、无页面脚本错误。证据：`.cache/desktop-validation/8f593aaa09a0439f89b6a57d7bcc16c7/report.json` 和 `.cache/frozen-ui-patch/5d927111e2454e5d96370e2356c621fd/report.json`。

历史 0.6.2 交付时，`dist/PersonalAiMemoryOs` 曾只更新四个兼容网页资源，原后端保持 0.6.1；备份记录为 `.cache/desktop-ui-update-result.json`。**0.6.3 新增了后端接口，不能沿用只覆盖网页的更新方式，必须使用完整新版程序。** 各便携目录的数据相互独立，不会自动读取其他目录资料。

历史 0.6.1 桌面工程验收于 2026-10-17 通过：全量测试 **696 项通过、3 项 Windows 符号链接权限用例跳过、1 条已有上游警告**；最终配置／存储专项与 16 项运行时测试通过；原有本机和 Docker 验收均退出 0。该版本发行 EXE 在实际 WebView2 155 窗口中通过资料和笔记管理、Markdown 导出／编辑／移动、JSON 导入及报告保存、重复双击、未保存关窗取消／退出、重启及完整目录移动。模拟调用在关窗后正常完成并保留草稿，没有自动生成笔记；真实模型调用为零。非法目录配置显示中文原生错误，没有在目录外创建数据库。正式文件哈希保持不变。

历史报告：`.cache/desktop-validation/08a46b518be848cfb14bc89742a6e1bd/report.json`。历史 0.6.1 EXE 的 SHA-256 为 `b61742bd5f3f2430734db40ca767a931309d6c8d34ddd3bac732e0dff19fe18d`；各版本校验值见对应 ZIP 的 `.zip.sha256`，当前 0.6.6 校验值已列在上方。正式 Docker 仍为 **0.6.0**，本轮没有重新部署或启用 AI/RAG；未进行第二台干净电脑和真实模型质量实测。

上述报告下载验收采用**测试模式自动保存**，退出后已确认导出的 JSON 仍然存在。独立生产模式检查已触发原生“另存为”流程的 `DownloadStarting`，但验证环境的原生控制通道不可用，尚未完成交互选择及保存后的文件复核，保留为人工核查项，不记为生产原生保存交互通过。证据 `.cache/desktop-native-download-review.json` 的状态为 `incomplete`；辅助检查的窗口和 HTTP 服务已正常关闭，没有遗留进程。

## 访问入口

| 入口 | 地址 |
| --- | --- |
| 中文管理工作台 | [http://127.0.0.1:18000/](http://127.0.0.1:18000/) |
| Swagger 接口文档 | [http://127.0.0.1:18000/docs](http://127.0.0.1:18000/docs) |
| 健康检查 | [http://127.0.0.1:18000/health](http://127.0.0.1:18000/health) |
| OpenAPI | [http://127.0.0.1:18000/openapi.json](http://127.0.0.1:18000/openapi.json) |

网页与 API 共用 FastAPI 服务，无需前端构建或 Node。当前没有账号和登录功能，部署保持仅监听本机回环地址。

## 快速启动

命令使用 Windows PowerShell，均在项目根目录执行。本机与 Docker 共享数据库和知识目录，应交替运行。

### 准备配置

首次使用时复制示例；以下命令会保留已有个人配置：

```powershell
Set-Location D:\VsCode\PersonalAiMemoryOs
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
if (-not (Test-Path -LiteralPath config/ai-providers.yml)) {
    Copy-Item config/ai-providers.example.yml config/ai-providers.yml
}
if (-not (Test-Path -LiteralPath config/embedding-providers.yml)) {
    Copy-Item config/embedding-providers.example.yml config/embedding-providers.yml
}
New-Item -ItemType Directory -Force data, knowledge | Out-Null
```

模型文件只是模板，需按实际服务配置。复制模板不会启用 AI 或 RAG。

### Docker 运行

需要 Docker Desktop、Linux 容器及 `docker compose`。若本机服务正在运行，先通过 `Ctrl+C` 停止。确认引擎可用后：

```powershell
docker info
docker compose build
docker compose run --rm --no-deps api /app/.venv/bin/alembic upgrade head
docker compose up -d api
docker compose ps
```

查看日志或停止服务：

```powershell
docker compose logs --tail 100 api
docker compose logs -f api
docker compose stop api
```

已有部署升级前，先停服并完成下文的备份，再构建、迁移和启动。普通 `docker compose down` 保留绑定目录及命名卷；不要对正式数据使用 `down -v`。

### 本机运行

需要 uv 0.13.0，使用项目内的 Python 3.12、虚拟环境和缓存。若 Docker API 正在运行，先执行 `docker compose stop api`。

```powershell
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PWD '.tools/python'
uv python install 3.12 --install-dir $env:UV_PYTHON_INSTALL_DIR --no-bin --no-registry
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:create_app --factory --host 127.0.0.1 --port 18000 --workers 1
```

通过 `Ctrl+C` 正常退出，切回 Docker 前先停止本机服务。重新打开 PowerShell 后，重新设置两个 uv 环境变量。

迁移必须显式执行：启动只检查数据库版本，不自动建表或升级。v0.5 升级 v0.6 没有新增迁移，仍使用 `0004`。

## 网页使用指南

| 页面 | 常用操作 |
| --- | --- |
| 概览 | 查看资料、笔记、待采纳草稿、冲突数量和服务状态 |
| 资料库 | 按标题分组、四项排序和分页跳转，阅读各篇回答，独立编辑、删除或恢复 |
| 资料导入 | 选择知乎 JSON 或 Markdown 文件夹，预演、提交并下载逐项报告 |
| 知识笔记 | 编辑 Markdown、摘要、分类、标签、概念和来源关联 |
| AI 草稿 | 选择来源和模型，生成、查看并采纳草稿 |
| 搜索问答 | 语义检索，查看引用回答并跳转笔记 |
| 同步与系统 | 查看文件问题、解决冲突、维护索引、查看模型配置状态 |

建议先创建一篇独立笔记，保存后检查 `knowledge/` 中自动生成的 Markdown 文件；再用外部编辑器修改正文，回到网页重新打开笔记查看同步结果。

一个 Source（原始资料）可关联多篇 Knowledge（知识笔记），也可创建无来源笔记。列表支持标题搜索和“正常／回收站／全部”。删除采用软删除，内容保留供恢复；有正常关联笔记的来源不能删除。恢复时若关联来源已删除，先恢复来源，或明确解除关联后恢复笔记。

保存成功表示数据库已保存，Markdown 可能仍在等待同步。并发编辑返回 409 时保留本地输入，需比较服务器版本后再操作。未保存离开会提示，后台轮询不会替换编辑字段。

Markdown 预览清除原始 HTML，不自动加载外部图片，仅允许安全链接协议。正文超过 100,000 字符时暂停预览，源码仍可完整编辑和保存。

## 数据目录与基础配置

| 路径 | 内容 |
| --- | --- |
| `data/memory.db` | 来源、笔记、处理记录和向量缓存 |
| `knowledge/` | Markdown 及 `.memory-os-vault` 身份标记 |
| `config/ai-providers.yml` | 个人文本生成模型配置 |
| `config/embedding-providers.yml` | 个人向量模型配置 |
| `.env` | 本机开关、密钥和环境配置 |
| `imports/` | 个人离线导入文件 |
| `.cache/` | 缓存、测试数据、报告和截图 |
| `.tools/python/`、`.venv/` | 项目内 Python 和虚拟环境 |

个人配置、密钥和运行数据不纳入版本控制，示例配置及自编样例纳入。Qdrant 使用 Docker 命名卷，由 Docker 管理，是项目内存储约定的已确认例外。

本机配置优先级：**环境变量 > 项目 `.env` > 默认值**。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `MEMORY_OS_DATABASE_URL` | `sqlite:///data/memory.db` | SQLite 文件，相对路径按项目根目录解析 |
| `MEMORY_OS_KNOWLEDGE_DIR` | `knowledge` | Markdown 目录 |
| `MEMORY_OS_SYNC_ENABLED` | `true` | 自动双向同步 |
| `MEMORY_OS_SYNC_INTERVAL` | `2` | 同步轮询间隔，秒 |
| `MEMORY_OS_DELETION_GRACE` | `10` | 文件缺失宽限，秒 |
| `MEMORY_OS_LOG_LEVEL` | `INFO` | 日志级别 |
| `MEMORY_OS_AI_ENABLED` | `false` | 文本生成开关 |
| `MEMORY_OS_RAG_ENABLED` | `false` | 索引与检索开关 |

Compose 固定容器数据库、知识目录和配置路径，挂载宿主机 `data/`、`knowledge/`，只读挂载 `config/`。其他变量是否从 `.env` 传入容器，以 `docker-compose.yml` 的 `environment` 为准；宿主机 `.env` 的全部变量不会自动进入容器。

## Markdown 双向同步

可在 `knowledge/` 下创建 UTF-8 文件：

```markdown
---
schema_version: 1
title: 数据库索引学习笔记
source_id: null
summary: 记录索引的收益与成本。
category: 数据库
tags: [数据库, 索引]
concepts: [B+树]
---
# 我的理解

索引减少查询扫描的数据量，也增加写入和存储成本。
```

新文件省略 `id`，系统导入后回填 UUID。已有文件必须保留 `id`，目录内部移动或改名不改变笔记身份。系统创建的文件默认以 UUID 命名。

- 默认每两秒扫描，文件连续两次观测稳定后处理。
- 文件连续缺失至少十秒并经过重复有效扫描，才同步软删除笔记。
- 同 UUID 文件重新出现可恢复原笔记；未完成操作、已删除来源或开放冲突可能阻止恢复。
- 已有笔记的 `source_id` 通过网页或 API 修改，不能通过 Markdown 改写。
- 重复 UUID、无效 YAML、未知身份等会保留文件并报告错误。
- 目录缺失、身份标记不匹配或扫描不完整时暂停同步，不解释为批量删除。

数据库和文件都偏离共同基线时，双方快照会保留。到“同步与系统”比较并选择系统版本或 Markdown 版本；任一方再次变化会返回 409，需要重新读取。

普通编辑器不共享应用写锁。系统保护已观测版本和已发现冲突，不能捕获两次扫描之间的每次保存，也不能完全消除并发文件替换窗口。

## 离线知乎导入

支持项目 JSON 和已适配的知乎 Markdown 导出格式，不会联网抓取、登录知乎或下载媒体。导入只创建 Source，不自动生成笔记。

### 从知乎 Markdown 文件夹导入

1. 打开实际要保存资料的桌面版或网页工作台，进入“资料导入”。桌面版与 Docker 使用各自配置的数据库，选择哪个工作台就导入到哪个库。
2. 切换到“知乎 Markdown 文件夹”，选择项目下的“知乎”目录，也可直接选择“我的收藏”或 `articles` 目录。目录选择不可用时，使用多选 Markdown 文件入口。
3. 点击“预演文件”，检查文件名、标题、作者、类型、预计新增、重复、差异和无效项。当前目录应识别 571 篇正文；README 和媒体文件不作为资料。
4. 点击“提交导入”，完成后下载报告，在“资料库”检查。再次导入会跳过已有对象，不覆盖修改或自动恢复已删除资料。

预演与提交使用同一份已读取内容，重新选目录或切换模式后需重新预演。每次最多 1,000 篇，整个 JSON 请求最多 10 MiB；超限请按收藏夹或子目录分次导入。读取或格式错误会逐项显示；数据库故障保留部分提交报告，网络中断不自动重试。

文件必须是 UTF-8（允许 BOM），开头包含 YAML frontmatter：

```markdown
---
id: "456"
title: 数据库索引学习
author: 示例作者
type: zhihu-answer
source: https://www.zhihu.com/question/123/answer/456
---
这里是自编示例正文，可以包含代码块和 Markdown 图片引用。
```

类型支持 `zhihu-answer`、`zhihu-article`、`zhihu-pin`，需与原文链接一致。分隔线后的正文完整保存，导出数字 ID 不当作系统 UUID，导出日期不覆盖系统时间。原文件不修改；图片留在原导出目录，软件不复制、不联网加载或展示，正文中的引用仍保留。

这是“原始资料库”，不会自动进入“知识笔记”或语义检索。需要时手动生成 AI 草稿并采纳，再由启用的 RAG 索引知识笔记。

### 从协议 JSON 导入

```json
{
  "schema_version": 1,
  "items": [
    {
      "url": "https://www.zhihu.com/question/123/answer/456",
      "title": "示例回答",
      "author": "示例作者",
      "content": "已经离线整理的原始正文，可以包含 Markdown。"
    }
  ]
}
```

输入为 UTF-8，支持 BOM，每批最多 10 MiB、500 条。`url`、`title` 和非空正文必填，`author` 可省略。支持回答、专栏文章和想法，按知乎对象类型与 ID 去重：重复资料跳过，变化报告差异，不覆盖已有来源或自动恢复已删除来源。单条无效不影响其他有效项，外层协议或 JSON 无效则拒绝整批。

网页先预演再提交，两步使用同一份已读取内容；换文件后重新预演。CLI 示例：

```powershell
uv run --locked python scripts/import_zhihu.py --file examples/zhihu-import.sample.json --dry-run
# 自己的文件放在 imports/，审阅预演后再去掉 --dry-run。
uv run --locked python scripts/import_zhihu.py --file imports/my-zhihu.json --dry-run
uv run --locked python scripts/import_zhihu.py --file imports/my-zhihu.json
```

CLI 默认提交到 `http://127.0.0.1:18000`，可用 `--base-url` 修改。文件必须位于项目内部，报告保存在 `.cache/import-reports/`。无效条目或请求失败会返回非零退出码；已经提交的有效项仍保留。503 部分提交报告需人工查看，不自动重新提交整批。

## 配置 AI 草稿生成

### 在设置中配置（0.6.6）

1. 点击左上“设置”，或桌面“设置 → AI 接口设置”；窄屏可直接点击顶部设置按钮。
2. 展开已有模型配置，或选择内置模板后点击“新建模型配置”。填写服务商提供的 API 前缀、模型 ID、协议、鉴权方式、密钥引用及输出限额；“高级参数”可维护 JSON 输出、Chat 限额字段、Anthropic 版本及 `extra_body`，已有参数会保留。
3. 密钥仅在新增或替换时输入。留空保留原值，已有值只显示“已配置”；多个模型共用同一引用时，替换影响全部共用配置。删除模型配置不会删除已保存密钥。
4. 勾选需要的模型配置，选择默认模型，按需设置文本生成 AI 开关，点击“保存设置”。完全退出再重新打开，新的设置才会生效；保存不会测试连接、调用模型、自动重启或打开 RAG。
5. 重启后先核对配置状态，再主动生成草稿。“配置就绪”不等于真实服务质量通过；现有正式 Docker 的 AI/RAG 仍保持关闭，不受其他便携目录设置影响。

未保存时离开会提示；遇到版本冲突会保留本地输入，确认“重新读取配置”才会丢弃并加载新版本。失败不自动重试。环境变量托管的值需在启动环境中修改；Docker 页面为只读，按下方手动配置方式操作。设置下方只读显示实际数据库、知识及配置目录，不提供改路径或搬移资料操作。

### 手动配置文件

也可修改 `config/ai-providers.yml`，选择实际服务的 API 地址、模型及默认 profile。适配器在 `base_url` 后追加接口路径，服务要求的 `/v1` 等前缀应保留在地址中：

| 协议 | 接口 | 配置样例 |
| --- | --- | --- |
| `openai_chat` | `/chat/completions` | OpenAI、DeepSeek、千问、硅基流动、豆包、Kimi、智谱及兼容服务 |
| `openai_responses` | `/responses` | OpenAI Responses 及兼容服务 |
| `anthropic_messages` | `/messages` | Claude Messages 及兼容服务 |
| `gemini_generate_content` | `/models/{model}:generateContent` | Gemini 原生接口 |

样例不代表所有厂商已经真实联调；模型 ID 和可选参数按实际服务填写。密钥在本机 `.env` 中配置：

```dotenv
MEMORY_OS_AI_ENABLED=false
MEMORY_OS_AI_CONFIG_FILE=config/ai-providers.yml
MEMORY_OS_AI_KEYS__DEEPSEEK=在本机填写自己的密钥
```

profile 的 `api_key_ref: deepseek` 对应 `MEMORY_OS_AI_KEYS__DEEPSEEK`。密钥不写入 YAML、数据库、浏览器存储或报告；设置密码框仅接收新值，不显示原值。新增自定义引用时，Docker 还需在 Compose 中显式传入对应变量。YAML `default_profile` 可由 `MEMORY_OS_AI_DEFAULT_PROFILE` 覆盖。

修改配置后重启；Docker 使用 `docker compose up -d --force-recreate api`。“配置就绪”只表示参数和必要密钥已配置，不证明接口连通或质量。正式 AI 保持关闭，隔离真实验收通过后再启用。

使用顺序：**选择正常资料和模型 → 主动生成 → 查看结果和依据 → 采纳为笔记 → 编辑并等待 Markdown 导出**。

生成和预览不创建 Knowledge 或文件。草稿采纳后才能编辑；来源已修改或删除时不能采纳旧草稿。重复采纳返回同一篇笔记，不自动恢复已删除笔记。

正文默认最多 20,000 字符，超限拒绝；默认输出上限 4,096 tokens、总时限 90 秒，实际以 profile 为准。草稿和问答共享一个文本生成并发额度，繁忙返回 429。失败、超时或断连不自动重试或切换服务；先查询处理记录，再决定是否新建调用。

DeepSeek 配置预检不会调用模型：

```powershell
uv run --locked python scripts/verify_real_provider.py --check
```

缺少密钥时退出码为 2。`--run` 会触发真实调用，仅在准备好并明确执行真实验收时使用。既定完整预算最多三次调用，每次最多 2,048 输出 tokens、90 秒，无自动重试；新建目录不会重置预算。三份样例及质量审阅均通过后才启用正式 AI。Embedding 和问答质量验收另行确定预算，不沿用该额度。

## 配置语义检索与引用问答

仅索引已提交的 Knowledge，不索引 Source 或未采纳草稿。在 `config/embedding-providers.yml` 中填写实际 API 地址、模型和 `dimension`。首版支持 `openai_embeddings`，可接本地兼容服务，应用不自动下载模型。

生成和向量模型分别配置。`dimension` 校验返回维度；只有服务支持且显式配置 `request_dimensions` 时才发送降维参数，两者必须相同。密钥继续使用 `MEMORY_OS_AI_KEYS__<引用>`。

启动可选 Qdrant：

```powershell
docker compose --profile rag up -d qdrant
```

固定镜像 `qdrant/qdrant:v1.19.2`。本机 API 默认访问 `http://127.0.0.1:6333`，Compose API 固定访问 `http://qdrant:6333`。连接宿主机模型时，容器内 `127.0.0.1` 无法指向宿主机，Docker Desktop 可按实际网络使用 `host.docker.internal`。

完成已授权的真实验收后，将 `.env` 中 `MEMORY_OS_RAG_ENABLED` 改为 `true`，再重启 API。启用后会自动为符合条件的笔记调用 Embedding，使用真实服务前应确认调用预算。语义搜索需要 RAG、Embedding 和 Qdrant；引用问答还需要启用并配置文本生成 AI。

- 默认每五秒对账，分块长度 1,200 字符、重叠 200 字符；每篇最多 100,000 字符、200 块，超限报错而不丢弃尾部。
- 已删除、存在开放冲突或同步错误的笔记不可检索；等待 Markdown 导出不阻止索引，文件移动不重新向量化。
- Embedding 失败、结果不明或中断后不自动重复付费调用，“重试失败项”需显式操作。
- 模型、revision、维度或分块规则变化，需要显式重建新代次。
- 无有效片段时返回依据不足，不调用生成模型；回答包含可追溯引用。生成期间笔记变化则返回 409。
- Qdrant 故障不影响已有资料管理、导入、文件同步和健康接口。

主要接口在 `/api/v1/rag` 下：`/embedding-profiles`、`/index/status`、`/index/run`、`/index/rebuild`、`/search`、`/ask`。查询最多 2,000 字符，`top_k` 默认 5、上限 10。完整请求类型见 Swagger。

## 备份与升级

停止使用同一存储的所有服务，再成对备份数据库和完整知识目录，包含 `.memory-os-vault`。下面适用于默认路径；本机服务需先通过 `Ctrl+C` 退出：

```powershell
docker compose stop api
$backupPath = Join-Path $PWD ('data/backups/manual-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backupPath | Out-Null
Copy-Item -LiteralPath data/memory.db -Destination (Join-Path $backupPath 'memory.db')
Copy-Item -LiteralPath knowledge -Destination (Join-Path $backupPath 'knowledge') -Recurse -Force
```

自定义路径时备份实际存储。个人 YAML 和 `.env` 可另行保存在受保护位置；Qdrant 命名卷不包含在上述复制中。恢复时先停服，同时恢复配对数据库和知识目录，再启动匹配版本代码。需要迁移的升级应在备份后显式执行 `alembic upgrade head`，不要迁移运行中的正式数据库。

## 测试与验收

自动测试使用项目 `.cache` 下的临时数据：

```powershell
uv sync --locked
uv run --locked pytest
```

网页完整验收需要 Docker 引擎、Qdrant 镜像和开发用 Chromium：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD '.cache/playwright'
uv run --locked playwright install chromium
uv run --locked python scripts/v06_acceptance.py --mode all
```

验收使用独立数据库、知识目录、离线模型和真实隔离 Qdrant，报告与截图保存在 `.cache/v06-validation/`，退出时清理自有进程、容器、网络和命名卷。生产镜像不包含 Playwright 或测试浏览器。

可单独运行 `uv run --locked python scripts/v06_editor_safeguards.py` 检查编辑保护，该脚本拦截全部 API，不访问数据库或真实模型。`scripts/check_web_modules.py` 是可选的 ESM 语法检查，仅该开发检查需要已有 Node，应用运行和构建不需要 Node。

2026-10-17 的 v0.6 工程验收记录为 **655 项通过、2 项 Windows 符号链接权限用例跳过、1 条已有上游警告**。本机与 Docker 的浏览器完整流程、重启和三种宽度布局均通过，真实模型调用为零。正式部署保持数据库 `0004`，没有导入验收样例，AI/RAG 保持关闭。以上为历史验收记录，不代表真实模型质量或当前数据数量。

详细结果及证据见 [IMPLEMENTATION_TASKS.md](../IMPLEMENTATION_TASKS.md) 和 [MEMORY.md](../MEMORY.md)。

## 常见问题

| 现象 | 检查方式 |
| --- | --- |
| 网页打不开 | 检查服务与 18000 端口；Docker 查看 `docker compose ps` 和 API 日志 |
| 启动提示迁移版本错误 | 停服备份，再执行对应运行方式的 `alembic upgrade head` |
| 已保存但没有文件 | 查看同步状态、待处理操作、文件错误、身份标记及目录权限 |
| 保存返回 409 | 保留本地输入，比较服务器版本后再提交，不直接替换版本号 |
| AI 或搜索按钮不可用 | 检查开关、profile、密钥、模型和地址；修改配置后重启 |
| 调用超时或断连 | 先查处理记录或索引错误，不自动重复提交 |
| 容器无法访问宿主机模型 | 使用容器可达地址，不能直接沿用宿主机 `127.0.0.1` |
| 健康正常但检索失败 | `/health` 检查数据库；另查 RAG、Embedding 与 Qdrant 状态 |

## 项目文档

| 文档 | 内容 |
| --- | --- |
| [SPEC.md](../SPEC.md) | 产品目标与范围 |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | 架构与分层 |
| [DATABASE_DESIGN.md](../DATABASE_DESIGN.md) | 数据模型与迁移 |
| [ROADMAP.md](../ROADMAP.md) | 阶段规划与状态 |
| [IMPLEMENTATION_TASKS.md](../IMPLEMENTATION_TASKS.md) | 任务及真实验收记录 |
| [MEMORY.md](../MEMORY.md) | 长期工程决策 |
| [AGENTS.md](../AGENTS.md) | 项目协作规则 |
