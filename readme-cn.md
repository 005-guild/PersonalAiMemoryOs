# Personal AI Memory OS — 完整中文使用手册

[English README](README.md) · [RAG 配置指南](docs/rag-guide-cn.md) · [全部配置参数](docs/config-reference-cn.md)

维护和后续工作见 [项目审阅与补充清单](docs/project-audit-cn.md)：包含当前实例版本、实际项目结构、优先事项、隔离恢复演练和校验矩阵。清单将已实现、待验收和可选扩展分开，不会因为登记待办就自动修改你的程序或调用模型。

适用版本：**0.8.0**；数据库版本：**0006**。新安装默认关闭 AI/RAG；当前电脑的固定桌面已按用户选择接通本地 BGE-M3 并开启 RAG，见下方实际配置说明。桌面安装固定在 `dist/PersonalAiMemoryOs-0.6.6/`；文件夹沿用原名，应用版本以窗口和接口显示为准。

应用的完整流程是：

**离线导入资料 → 浏览原文 → AI 生成草稿 → 人工采纳 → 编辑知识笔记 → Markdown 双向同步 → 向量索引 → 语义搜索与引用问答。**

也可以直接手工新建笔记，完全跳过导入和 AI 草稿。

<a id="contents"></a>
## 目录与按需查找

| 你想做什么 | 直接阅读 |
| --- | --- |
| 第一次使用，先让程序运行 | [1. 功能与基本概念](#basics)、[2. 安装与启动](#start) |
| 确认数据到底保存在哪 | [3. 目录与数据隔离](#storage) |
| 管理资料、同标题回答、分页排序 | [5. 资料库](#sources) |
| 批量导入知乎 Markdown 或 JSON | [6. 资料导入](#imports) |
| 编辑笔记、批量删除、恢复 | [7. 知识笔记](#knowledge) |
| 填写 DeepSeek 等 AI 接口 | [8. AI 配置](#ai)、[完整配置参考](docs/config-reference-cn.md) |
| 提交分析、检查并采纳草稿 | [9. AI 分析与草稿箱](#drafts) |
| 单独管理解析和问答 Prompt | [9.2 Prompt 中心](#prompt-center) |
| 用外部编辑器维护 Markdown | [10. Markdown 同步](#markdown) |
| 开启 RAG，需要哪些服务、怎么填 | [11. RAG 配置与启用](#rag)、[逐步配置指南](docs/rag-guide-cn.md) |
| 搜索、提问、阅读引用 | [12. 搜索与问答](#search) |
| 处理同步冲突和索引错误 | [13. 同步与系统状态](#system)、[16. 排错](#troubleshooting) |
| 换电脑、升级 EXE、备份恢复 | [14. 备份、恢复与升级](#backup) |
| 用脚本或 Swagger 调用接口 | [15. 接口与命令](#api) |
| 查所有环境变量与 YAML 字段 | [完整配置参考](docs/config-reference-cn.md) |
| 查功能限制与验收范围 | [17. 限制与工程记录](#limits) |
| 查看后续补充、恢复演练与维护计划 | [项目审阅与补充清单](docs/project-audit-cn.md) |

<a id="basics"></a>
## 1. 功能与基本概念

### 1.1 三种内容分别是什么

| 名称 | 保存什么 | 从哪里产生 | 是否进入 RAG |
| --- | --- | --- | --- |
| 资料 Source | 原文、标题、作者、原文链接和来源类型 | 手工新建、知乎 JSON／Markdown 导入 | 不直接进入 |
| 草稿 Processing Run | 某次 AI 调用的来源快照、结构化结果、笔记预览和用量 | 主动点击“生成知识草稿” | 不进入 |
| 知识笔记 Knowledge | 可以长期编辑的标题、摘要、分类、标签、概念和 Markdown 正文 | 手工创建、符合协议的外部 Markdown、采纳草稿 | 启用 RAG 后按条件索引 |

一份资料可以关联多篇笔记；一篇笔记可关联最多 20 份资料，也可以没有来源。**导入 571 篇资料不等于生成了 571 篇知识笔记**。相同标题显示成一组，只改变资料列表的展示，不合并原始记录。

资料和笔记保存在本机，但配置外部模型后，生成会把相关原文、索引会把笔记检索文本、搜索会把查询、问答会把问题及选中片段发往你配置的服务。本机运行不等于模型处理也完全离线；本地模型服务同样需要单独准备。

### 1.2 哪些功能需要配置模型

| 功能 | 文本生成 AI | Embedding | Qdrant | 功能开关 |
| --- | --- | --- | --- | --- |
| 资料管理、离线导入、笔记编辑、Markdown 同步 | 不需要 | 不需要 | 不需要 | 同步另有开关 |
| 生成知识草稿 | 需要 | 不需要 | 不需要 | `AI_ENABLED=true` |
| 语义搜索 | 不需要 | 需要 | 需要 | `RAG_ENABLED=true` |
| 引用问答 | 需要 | 需要 | 需要 | AI 和 RAG 都开启 |

表中的开关都带 `MEMORY_OS_` 前缀。AI 和 RAG **默认关闭**。

**Embedding 是向量模型服务，不是另一个聊天模型名称。** DeepSeek 文本生成配置不会自动成为 Embedding 配置。应用不自带模型、不自动下载模型，也不自带 Qdrant。

### 1.3 第一次建议怎么走

1. 先用默认关闭 AI/RAG 的状态启动，创建一篇笔记，确认能保存及生成 Markdown。
2. 将知乎导出目录预演并导入，去资料库核对原文。
3. 在左上角设置中配置文本生成模型，重启后生成一篇草稿并采纳。
4. 需要搜索时再按 [RAG 指南](docs/rag-guide-cn.md) 配置向量模型和 Qdrant。
5. 先用少量笔记检查效果，再扩大知识库。启用 RAG 会自动索引，可能调用收费服务。

<a id="start"></a>
## 2. 安装与启动

### 2.1 选择运行方式

| 方式 | 适合谁 | 必要环境 | 访问入口 | 默认数据位置 |
| --- | --- | --- | --- | --- |
| Windows 便携 EXE | 日常桌面使用 | Windows x64、WebView2、.NET Framework 4.8 | 独立窗口 | EXE 所在目录 |
| 本机 Python | 开发、调试、脚本操作 | Python 3.12，由 uv 管理 | `http://127.0.0.1:18000/` | 项目根目录 |
| Docker Compose | 通过容器运行后端 | Docker 引擎、Linux 容器、Compose v2 | `http://127.0.0.1:18000/` | 项目绑定目录 |

本机 Python 与项目 Compose 默认共享 `data/`、`knowledge/`，应交替运行。EXE 的便携数据独立，默认不会读取项目数据。

当前没有账号、登录或多用户权限管理，按本机使用设计；保持回环地址发布。本文的配置命令是供你执行的操作说明，不表示现有 Docker 已经升级。

### 2.2 Windows 便携 EXE

1. 新安装完整解压 `dist/PersonalAiMemoryOs-windows-x64.zip` 到可写目录；已有安装按[原地升级](#backup)处理。
2. 保留整个 `PersonalAiMemoryOs-0.6.6/`，包括 `_internal/`。
3. 双击 `PersonalAiMemoryOs.exe`。基础管理无需安装 Python、uv 或 Docker。
4. 首次运行补齐缺失配置并创建空库；已有配置不会被模板覆盖。
5. 通过左上角“设置”进入 AI 配置；桌面菜单可打开数据、知识、配置和日志目录。

不要只复制 EXE。不要在 ZIP 预览内直接运行，也不要放在只读目录中。

桌面后端只监听 `127.0.0.1`，使用随机空闲端口，不固定占用 18000。同一便携目录重复双击会唤起已有窗口；不同便携目录数据独立。

缺少 WebView2 或 .NET 运行环境时，程序会显示中文提示和微软下载入口，不自动安装。WebView2 下载见 [微软官方网站](https://developer.microsoft.com/microsoft-edge/webview2/)。

关闭窗口时，未保存修改会提示；在途调用和同步会等待正常结束，超过 150 秒继续显示等待状态，不自动强杀。请等程序退出后再复制、备份或移动目录。

### 2.3 本机 Python 启动

以下命令在项目根目录运行。项目使用 Python 3.12 和锁文件；此前工程环境使用 uv 0.13.0。

先准备缺失文件，保留已有个人配置：

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

停止使用同一存储的 Docker API，安装依赖、迁移，再启动：

```powershell
docker compose stop api
$env:UV_CACHE_DIR = Join-Path $PWD '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PWD '.tools/python'
uv python install 3.12 --install-dir $env:UV_PYTHON_INSTALL_DIR --no-bin --no-registry
uv sync --locked
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:create_app --factory --host 127.0.0.1 --port 18000 --workers 1
```

若未使用 Docker，可省略停止容器命令。`Ctrl+C` 正常退出；重新打开 PowerShell 后重新设置上述 uv 路径变量。已有库执行迁移前先 [停服备份](#backup)。

普通 Python 启动只检查数据库版本，**不会自动迁移**。桌面 EXE 的空库初始化和经确认的旧库升级属于独立启动流程。

### 2.4 Docker 启动

在包含 `docker-compose.yml` 的项目根目录执行；便携 EXE 目录没有这份 Compose 文件。

先按上一节准备个人配置，停止使用同一数据的本机服务。首次启动或已停服备份后的升级：

```powershell
docker info
docker compose build
docker compose run --rm --no-deps api /app/.venv/bin/alembic upgrade head
docker compose up -d api
docker compose ps
```

常用维护命令：

```powershell
docker compose logs --tail 100 api
docker compose logs -f api
docker compose stop api
```

修改宿主机 YAML 或 `.env` 后：

```powershell
docker compose up -d --force-recreate api
```

仅 `docker compose restart api` 不会重新注入变更后的 Compose 环境变量。应用代码变更需重新构建镜像；普通配置变更一般只需重新创建服务。

普通 `docker compose down` 保留命名卷。**`docker compose down -v` 会删除 Compose 命名卷**，包括 Qdrant 数据，不作为日常停止命令使用。

### 2.5 网页和接口地址

本机 Python／Compose 默认：

| 入口 | 地址 |
| --- | --- |
| 管理工作台 | [http://127.0.0.1:18000/](http://127.0.0.1:18000/) |
| Swagger | [http://127.0.0.1:18000/docs](http://127.0.0.1:18000/docs) |
| OpenAPI | [http://127.0.0.1:18000/openapi.json](http://127.0.0.1:18000/openapi.json) |
| 健康检查 | [http://127.0.0.1:18000/health](http://127.0.0.1:18000/health) |

EXE 使用其自己的随机端口；上表的 18000 可能是另一个库，不要因浏览器能打开就认为访问的是桌面资料。

<a id="storage"></a>
## 3. 目录、配置优先级与数据隔离

### 3.1 哪些文件属于你

下表相对于**当前运行根目录**；桌面为 EXE 所在目录，本机和默认 Compose 为项目目录。

| 路径 | 内容及用途 |
| --- | --- |
| `.env` | 开关、密钥和运行配置，包含明文凭据 |
| `config/ai-providers.yml` | 文本生成模型配置，不保存密钥 |
| `config/embedding-providers.yml` | 向量模型配置，不保存密钥 |
| `data/memory.db` | 原始资料、笔记、草稿、同步记录、索引任务和成功向量缓存 |
| `knowledge/` | 知识笔记 Markdown 及目录身份标记 |
| `knowledge/.memory-os-vault` | 与数据库配对的目录身份，必须保留 |
| `logs/memory-os.log` | 桌面轮转日志；本机／容器通常看终端／容器日志 |
| `.cache/desktop/` | 桌面窗口、浏览器及运行缓存 |
| `.cache/import-reports/` | 本机导入命令生成的结果报告 |
| `backups/` | 桌面数据库升级时的备份（有升级才产生） |
| `.memory-os-config-transactions/` | 配置写入中断时的恢复记录，可能含凭据，不能公开 |
| `imports/` | 项目中可放个人 JSON 输入；网页导入不要求位于此目录 |
| Qdrant 命名卷 | 向量检索数据，由 Docker 管理，不在上述文件夹中 |

这些是默认位置；实际位置可在“设置”下方查看，或通过桌面“工作空间”菜单打开。桌面版数据库、知识和配置路径必须留在该便携目录内。

`_internal/` 是程序资源，不是个人配置目录。不要在其内部编辑 `.env.example`、YAML 模板或数据库。

### 3.2 优先级和生效方式

**启动进程的环境变量 > 运行根目录的 `.env` > 默认值。** YAML 提供 profile；可选的 `MEMORY_OS_AI_DEFAULT_PROFILE`、`MEMORY_OS_EMBEDDING_DEFAULT_PROFILE` 优先于 YAML 默认项。

模型运行配置在启动时加载。网页保存、外部编辑 YAML 或 `.env` 后需重启；刷新网页不会重新加载后端配置。SQLite 中的提示词模板保存立即供新任务使用，不需要重启。

Compose 只传入 `environment:` 中显式列出的变量。宿主机 `.env` 有一个值，不代表该值已经进入容器。目录、开关和高级参数的完整对照见 [配置参考](docs/config-reference-cn.md)。

<a id="navigation"></a>
## 4. 工作台导航与通用操作

| 页面 | Hash 路由 | 用途 |
| --- | --- | --- |
| 设置 | `#/settings` | 编辑 AI／RAG 配置、主动连接测试、查看运行和存储位置 |
| 概览 | `#/` | 查看实际数量、状态和常用入口 |
| 资料库 | `#/sources` | 同标题分组、分页排序、查看和维护各条资料 |
| 资料导入 | `#/imports` | 知乎 Markdown／JSON 预演、提交和报告 |
| 知识笔记 | `#/knowledge` | 新建、编辑、预览、批量软删除和恢复笔记 |
| AI 分析 | `#/processing` | 选择资料、生成参数、提交和查看任务 |
| 草稿箱 | `#/drafts` | 待采纳／已采纳草稿列表，独立详情与采纳 |
| Prompt 中心 | `#/prompts` | 管理笔记解析与知识库问答两类模板 |
| 搜索问答 | `#/search` | 语义搜索和单轮引用问答 |
| 同步与系统 | `#/system` | 同步、冲突、索引任务和配置就绪状态 |

右上“API 文档”打开 Swagger。窄屏导航可以收起，顶部也有直接设置入口。列表和详情在同一工作台中切换，刷新 Hash 详情路由仍可定位。

通用规则：

- 修改、删除、恢复使用读取时的版本号。409 表示内容或状态已变化，保留当前输入并比较最新版本，不能盲目覆盖。
- 未保存修改时，切换记录、离开页面或关窗会提示。后台轮询不覆盖编辑框。
- “数据库已保存”不等于“Markdown 已同步”；保存后可在同步状态中确认。
- 生成、问答和索引维护按钮不会自动重复提交；失败不自动重试模型。
- 普通文本按文本显示，Markdown 经安全清洗；外部图片不自动加载，原始 HTML 不执行。
- 支持常规键盘 Tab、Enter 和页面中的按钮操作。AI 页支持显式批量生成；没有未标出的快捷保存操作。

概览的“原始资料”统计正常 Source 条数，不是资料库标题组数。“待采纳草稿”统计 ready 记录，其中可能有因来源过期而不能采纳的草稿。概览还展示最近 5 篇笔记和常用入口；进入具体记录确认可用状态。

<a id="sources"></a>
## 5. 资料库：分页、同标题分组、排序与回收站

### 5.1 浏览和查找

1. 打开“资料库”，输入标题关键词。匹配标题中的字面包含内容，不是语义搜索。
2. 选择“正常／回收站／全部”。
3. 选择排序项：标题、资料数量、来源类型、更新时间；可选升序／降序，也可点击列标题。
4. 选择每页 10／20／50／100 个标题；点击数字页码，或输入页码跳转。

筛选后先按**完全相同的标题**分组，排序整个结果，再分页。默认更新时间降序；切换排序回到第一页。列表页数按标题组计算，不按原始回答总数计算。

标题和类型按数据库字符顺序排序，不是中文拼音。类型排序使用 `Source.source_type`（例如 `zhihu`、`manual`），不是回答／文章／想法；全是知乎资料时这项通常相同。混合类型组按当前可见成员中字符顺序最前的来源类型排序。

### 5.2 同题下有多篇回答

点击标题进入组内，分别查看每条资料的作者、原文链接和摘要，按需展开全文。组内每页可选 10／20／50／100 篇；不会为一页 100 篇自动请求全部正文。可以针对某一条编辑、生成草稿或查看关联笔记和处理记录。

“关联笔记”仅筛选已有笔记。从该筛选页再点“新建笔记”不会自动继承关联，仍需在编辑器中手动选择来源。

记录的 UUID、正文和版本仍然独立。同标题不会合成一篇文章，也不会共用一份 AI 草稿。详情返回会保留列表／组内的位置和筛选条件。

### 5.3 新建、编辑、删除与恢复

手工资料可维护来源类型、标题、作者、链接和正文。手工创建允许正文为空，但空正文不能生成 AI 草稿。通用资料 API 不按相同 URL 自动去重；知乎导入有独立身份去重机制。

删除是软删除，记录进入回收站。存在未删除关联笔记时，后端会阻止删除资料。可先处理关联笔记或解除关联；不会级联删笔记。

恢复资料不会自动恢复它的所有笔记。资料页目前不提供知识笔记那样的批量删除，也没有物理清空回收站功能。

<a id="imports"></a>
## 6. 知乎离线批量导入

### 6.1 导入能力和格式区别

应用不会登录知乎、在线抓取收藏夹或下载图片。你需先通过外部方式取得已整理的文件。

| 入口 | 允许内容 | 每批上限 |
| --- | --- | --- |
| 知乎 Markdown 文件夹／多选文件 | 已适配的知乎回答、文章、想法 Markdown | 1,000 篇，整个请求 10 MiB |
| 项目 JSON | schema_version 1 的资料数组 | 500 条，整个请求 10 MiB |

均采用 UTF-8，允许 BOM。目录索引 README、图片和进度文件不作为资料。10 MiB 是序列化后的整个 JSON 请求大小，不等同于磁盘文件大小总和。

**知乎导入 Markdown 和知识目录 Markdown 是两种协议。** 原始导出文件从“资料导入”进入；不要把它们直接复制到 `knowledge/` 期望自动成为资料库。

### 6.2 从文件夹导入

1. 打开实际要保存数据的工作台，进入“资料导入”。
2. 选择“知乎 Markdown 文件夹”，选择根目录或收藏夹子目录；也可使用多选 Markdown 文件。
3. 点击“预演文件”，查看预计新增、重复、差异、无效项以及对应文件名。
4. 确认后点击“提交导入”。
5. 下载报告，到“资料库”核对。报告不包含原文正文。

预演不写数据库，提交使用预演时读取的同一份内容。重新选择目录／文件后，旧预演失效，需要重做。当前项目曾用 571 篇样本验收；你的其他目录数量以本次预演为准。

自编格式示例：

```markdown
---
title: 数据库索引学习
author: 示例作者
type: zhihu-answer
source: https://www.zhihu.com/question/123/answer/456
---
这里是完整 Markdown 正文，可以包含中文、代码块和图片引用。
```

`title` 和 `source` 必需；`author` 可省略。`type` 可省略；填写时只能为 `zhihu-answer`、`zhihu-article`、`zhihu-pin`，并需与 URL 一致。数字 `id` 不是系统 UUID，若填写需与知乎对象匹配。导出日期不覆盖系统创建／更新时间。

正文保留，原始文件不修改。图片引用保留在正文中，但图片不上传、不复制、不自动联网加载。未知导出元数据可能作为警告报告，不变成数据库字段。

### 6.3 从 JSON 导入

```json
{
  "schema_version": 1,
  "items": [
    {
      "url": "https://www.zhihu.com/question/123/answer/456",
      "title": "示例回答",
      "author": "示例作者",
      "content": "这里是已经离线整理的完整正文。"
    }
  ]
}
```

`url`、`title`、非空 `content` 必填，`author` 可省略。接受回答 `/question/{id}/answer/{id}`、文章 `/p/{id}` 和想法 `/pin/{id}` 对应链接。

网页流程同样是选择文件 → 预演 → 提交 → 下载报告。JSON 协议样例见 [examples/zhihu-import.sample.json](examples/zhihu-import.sample.json)。

### 6.4 重复、差异和部分失败

按知乎对象类型＋对象 ID 识别；同问题下的不同回答分别保留。查询参数变化不创建新对象。

- 已登记对象再次导入：跳过，不覆盖；标题／作者／正文变化时报告差异字段。
- 已软删除的资料：跳过，不自动恢复。
- 既有手工资料 URL 匹配：报告匹配并跳过，不自动合并或接管。
- 单条无效：其他有效项继续；外层协议、JSON 或编码无效：拒绝整批。
- 数据库故障可能已有部分条目提交：保留并展示部分报告，不将它误认为全批回滚。
- 断连后先查资料和报告，再决定是否重新提交；界面不会自动重试。

导入只创建 Source。需要语义检索的内容，要先生成并采纳成 Knowledge，或手工整理为知识笔记。

<a id="knowledge"></a>
## 7. 知识笔记：编辑、预览、批量删除与恢复

### 7.1 新建和编辑

1. 打开“知识笔记”，新建笔记。
2. 填标题和 Markdown 正文；可补充摘要、分类、标签、概念。
3. 可选择资料来源，也可不关联来源。来源查找支持标题搜索和分页。
4. 保存成功自动返回概览首页；没有修改时点保存也返回。Markdown 在后台同步，失败或版本冲突时保留编辑输入。

分类是自由文字，例如“数据库／工程实践”，不是固定分类树。网页标签和概念按中文逗号、英文逗号或换行分隔并去重；需要把逗号作为单个标签内容时，不宜用该网页输入方式重新编辑。

笔记列表可按标题、来源和“正常／回收站／全部”筛选，支持 10／20／50／100 条每页、数字页码及输入页码跳转。筛选、修改每页条数后从第一页开始，返回列表保留位置。删除导致当前页变空时自动调整到有效页。

### 7.2 Markdown 预览

正文使用源码编辑，预览支持中文、列表、引用和代码块。原始 HTML 不执行，危险链接会清洗，外部图片不自动加载。

正文超过 **100,000 字符**时暂停预览；仍可完整编辑和保存，不会截断。这与 Source 默认 20,000 字符的 AI 输入上限、RAG 默认 100,000 字符的组合检索文本上限分别独立。

### 7.3 列表批量删除

不必进入每篇详情：

1. 在正常笔记列表勾选需要的笔记，或选择当前页全部。
2. 点击批量删除并确认。
3. 查看成功／失败的逐项结果。

“全选”只选当前页，翻页或筛选会清空选择。回收站记录不可勾选。每篇独立校验版本；某篇 409 不会覆盖它，其他篇可继续。网络或服务器故障会停止尚未提交的项，不自动重试；已经成功的删除不回滚。

### 7.4 恢复

回收站中打开笔记并恢复。关联 Source 已删除时，需要先恢复来源，或按界面明确解除关联后恢复。恢复不自动覆盖被其他文件占用的 Markdown 路径。

采纳过的笔记即使被删除，也不会因重复采纳同一草稿自动复活。需要从笔记回收站恢复。

<a id="ai"></a>
## 8. 文本生成 AI：DeepSeek 与其他 API

### 8.1 从界面配置

1. 点击工作台左上角“设置”，或桌面“设置 → AI 接口设置”。
2. 展开已有模型配置，或选择模板后“新建模型配置”。
3. 填写配置 ID、显示名称、协议、API 地址前缀、模型 ID、密钥引用和 API 密钥。
4. 根据服务要求选择鉴权方式、输出 Token 上限和调用超时。
5. 在“高级参数”设置 JSON 输出、Chat Token 字段、Anthropic 版本及扩展 JSON。
6. 勾选该模型配置、选择默认配置，按需开启文本生成 AI。
7. 保存成功若需重启，会询问“现在重启／稍后”。EXE 选择现在重启可在同目录正常退出并重开；稍后保留已保存配置。Python／Docker 按提示手动重启。

新建模板不会联网探测，也不会自动开启。配置 ID 是小写字母开头、最多 64 字符的标识；它与供应商模型 ID 是两个字段。

密码框留空保留已有值；只有填写新值才替换密钥。多个 profile 共用同一密钥引用时，替换会影响它们。删除 profile 不删除本机保存的密钥。

保存不调用模型、不热加载，也不启用 RAG。只有确认“现在重启”才执行桌面重启，未保存内容仍需确认退出；在途调用会等待结束。“配置就绪”只表示参数和所需密钥齐全，不表示认证、余额、接口连通或生成质量已经验证。

### 8.2 DeepSeek 默认值和思考模式

软件内置模板：

| 项目 | 默认值 |
| --- | --- |
| 协议 | `openai_chat` |
| API 前缀 | `https://api.deepseek.com` |
| 模型 | `deepseek-flash` |
| 密钥引用 | `deepseek` |
| JSON 模式 | `json_object` |
| 输出上限／超时 | 4,096 tokens／90 秒 |
| 思考模式 | 显式关闭 |

“高级参数 → 扩展请求参数”默认：

```json
{"thinking": {"type": "disabled"}}
```

要开启思考，可改成：

```json
{"thinking": {"type": "enabled"}}
```

保存并重启。模型名不需要因这项开关自动改变；应用只读取最终回答，不展示思考内容。官方参数见 [DeepSeek 思考模式说明](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)。模型可用性以你所用服务为准，兼容平台不要直接照搬官方模型 ID。

### 8.3 四种协议和 API 地址

| 协议 | 应用追加的路径 | 适用配置 |
| --- | --- | --- |
| `openai_chat` | `/chat/completions` | DeepSeek、OpenAI Chat 及各类兼容服务 |
| `openai_responses` | `/responses` | Responses 兼容服务 |
| `anthropic_messages` | `/messages` | Claude Messages 兼容服务 |
| `gemini_generate_content` | `/models/{model}:generateContent` | Gemini 原生兼容接口 |

填 API **前缀**，不是完整的 `/chat/completions` 请求地址。服务要求 `/v1` 等前缀时应保留，避免被重复追加路径。具体鉴权和可选参数不能仅因“兼容”就假设一致。

### 8.4 手动文件配置与 Docker

文本 profile 保存于 `config/ai-providers.yml`；开关和密钥位于 `.env`：

```dotenv
MEMORY_OS_AI_ENABLED=true
MEMORY_OS_AI_CONFIG_FILE=config/ai-providers.yml
MEMORY_OS_AI_KEYS__DEEPSEEK=在本机填写真实密钥
```

`api_key_ref: deepseek` 对应 `MEMORY_OS_AI_KEYS__DEEPSEEK`。不要把密钥放 YAML、聊天或代码里；`.env` 是明文个人配置，备份也需保管。

Docker 设置页只读；编辑宿主机文件后重新创建 API。自定义密钥引用还需在 Compose 中显式透传对应变量。环境托管项以环境变量为准，网页不能替你覆盖。

所有字段、鉴权映射、可用范围和扩展参数禁用项见 [完整配置参考](docs/config-reference-cn.md)。

<a id="drafts"></a>
## 9. AI 分析与草稿箱

### 9.1 选择资料与处理方式

1. 进入“AI 分析”，在复选列表按标题搜索资料，每页可选 10／20／50／100 篇，可点页码或输入页码跳转。
2. 单独勾选或“当前页全选”，跨页和搜索保留选择；最多 20 篇，顶部显示已选数量，可清空。
3. 点击资料“预览”读取完整正文。选择列表按独立 Source 展示，不受资料库同标题分组影响。
4. 选择就绪模型、Prompt 模板和处理方式。**逐篇生成**为每篇独立调用、产生独立草稿；**合并分析**将全部所选资料发送一次，产生一份综合草稿。
5. 核对资料清单、调用次数、输出 tokens 和超时，再主动提交。默认深度解析预填 **16,384 tokens／180 秒**；可修改，不改变模型配置中的思考模式。
6. 提交后显示持久任务与逐项进度。离开页面不取消任务，返回可继续查看。历史运行的来源／状态／模型筛选与选择资料分别独立。

逐篇模式逐条校验输入上限；合并模式按所有资料正文总长度校验。默认上限 20,000 字符，可配置，超限拒绝且不截断。token 上限不是保证输出长度；开启思考时还需核对供应商的预算规则，截断不会产生笔记。

<a id="prompt-center"></a>
### 9.2 深度解析与独立 Prompt 中心

左侧“Prompt 中心”可搜索、新建、编辑、复制、预览、设默认或归档模板，按“笔记解析”和“知识库问答”分开管理，各有自己的默认项和修订历史。用途创建后固定；AI 分析只选解析模板，引用问答只选问答模板。

笔记解析内置完整的[知乎观点深度解析 Prompt](app/prompts/zhihu_deep_analysis_v1.md)为默认，保留八阶段：理解作者、拆解论证、事实逻辑、成立边界、作者视角、综合认知、个人行动、最终判断。另保留简要整理模板。问答模板可定制语气、重点、解释方式；只用知识库证据、逐段引用、原文摘录和固定输出合同仍统一校验。

本版**不联网核验**。运行约束要求模型区分原文、推论与外部知识，无法确认的关键事实标记待验证，不编造已核实来源。输出里的原文引文逐字匹配对应资料；这一检查不能代替人工评价分析质量。

模板内容最多 100,000 字符，具有版本历史；保存立即生效，只影响新提交任务。已提交任务冻结模板、模型配置、生成参数和资料快照，后续编辑模板不会改变旧任务。默认使用 JSON v2 完整 Markdown 正文；旧 v1 草稿与简要整理仍可查看、采纳。

### 9.3 暂停、取消、继续与重试

| 批任务状态 | 含义 |
| --- | --- |
| `pending` / `running` | 已持久保存／正在逐项执行 |
| `paused` | 系统错误、退出或重启后暂停；需要明确操作 |
| `cancelling` / `cancelled` | 不再开始后续调用；当前调用正常收尾 |
| `completed` | 本轮全部处理结束，仍需检查各项成功或失败 |

输出格式、原文证据或拒答问题记为单项失败后继续；网络、上游、超时、鉴权、限流、输出截断或未知系统问题会暂停整批。每次调用前核对资料版本；来源修改或删除不会继续消耗该次调用，合并分析任一来源变化即停止。

“继续待处理”只处理尚未调用的条目；“重试失败项”会再次调用模型，需单独确认。退出或重启不自动重发付费调用。客户端断连先查任务记录；相同请求标识的相同提交返回原任务，不能用不断新建请求的方式排错。

若提示正文为空或超过输入上限，先检查资料原文和 AI 分析区显示的正文字符数。逐篇模式按每篇校验，合并模式还校验所有正文总和；增加分页条数不会扩大输入上限。需要分析长文时，可减少本次选中资料，或在当前运行目录的 `.env` 调整 `MEMORY_OS_AI_MAX_INPUT_CHARS` 后重启，并核对模型实际上下文额度。程序会显示出错资料、实际字符数与上限，不会自动截断或发出被拒绝的模型调用。

### 9.4 审阅与采纳

在独立“草稿箱”按标题、状态、来源或模型查找草稿；列表只呈现可审阅的待采纳与已采纳结果。打开独立详情查看来源快照、摘要、分类、完整正文、引文、结束原因和用量，核对后采纳。运行中、失败和中断项从 AI 分析的任务记录查看。采纳仍先进入笔记编辑，保存后返回首页；合并草稿关联全部来源。

**生成和预览不会创建知识笔记或 Markdown。** 采纳才产生新 Knowledge。重复或并发采纳同一草稿返回原笔记，不重复创建。

| 状态 | 含义与下一步 |
| --- | --- |
| `running` | 模型调用中，查询现有记录，避免重复提交 |
| `ready` | 已生成、待审阅；来源未过期才能采纳 |
| `adopted` | 已采纳，可打开对应笔记 |
| `failed` | 调用或结果验证失败，查看错误后自行决定是否新建调用 |
| `interrupted` | 启动时发现上次未完成的调用，不会自动重新调用 |

任一关联 Source 的版本变化或软删除都可能让草稿过期；不是只有正文变化才过期。采纳时检查全部来源，需基于最新 Source 重新生成，旧结果保留以便查看。

模型输出必须满足结构和原文依据验证；无效 JSON、空摘要、截断、拒答或无效依据会失败，不创建笔记。v2 完整正文不再只由要点重组；旧 v1 继续用“原文观点／依据／AI 分析”渲染。

草稿与问答共享一个文本生成并发名额，批次严格串行；繁忙返回 429。模型调用在锁和长数据库事务外，普通资料管理不必等待模型完成。

每篇运行仍保留 `running/ready/adopted/failed/interrupted` 状态。批次中的单项可打开对应运行；新旧草稿均保留，不因切换模板而丢失。

<a id="markdown"></a>
## 10. Markdown 双向同步与外部编辑

### 10.1 新建知识文件的最小协议

在当前 `knowledge/` 内新建 UTF-8 `.md`，例如：

```markdown
---
schema_version: 1
title: 我的索引学习笔记
source_id: null
summary: 索引是一种有读写权衡的数据结构。
category: 数据库
tags: [MySQL, 索引]
concepts: [B+树]
---
# 我的理解

索引减少查询扫描量，也可能增加写入和存储成本。
```

新文件省略 `id`，系统创建后回填笔记 UUID；不是知乎导出数字 ID。摘要、分类、标签、概念可省略；`schema_version: 1` 和标题必需。正文在 frontmatter 结束分隔线后，不写成 YAML 的 `body` 字段。

已有笔记必须保留 `id`。创建时可填正常 Source 的 UUID；之后改来源关联请用网页／API，不通过 Markdown 改 `source_id`。

多来源笔记使用 `schema_version: 2` 和有序 `source_ids: [UUID1, UUID2]`，其余字段与 v1 一致；最多 20 个不同来源。可选 `source_id` 若填写须与首项一致。既有单来源 v1 文件和同步基线不批量改写；新增或更改为多来源才导出 v2。创建后来源关联仍通过网页／API维护，不能通过手改 frontmatter 接管其他来源。

未知 frontmatter 字段、重复键、无效 YAML、未知 UUID、重复 UUID 或不允许的字段变化会报告问题，不自动猜测修复。

### 10.2 改名、移动、删除与恢复

- 自动生成文件默认叫 `<笔记UUID>.md`，在知识根目录内部改名或移入子目录按 UUID 保持身份。
- 外部正文或元数据编辑，在文件连续两次稳定扫描后回写数据库；默认扫描间隔 2 秒。
- 文件连续缺失至少 10 秒且经过重复有效扫描后，才同步软删除笔记。把文件移出知识目录也属于缺失。
- 相同 UUID 文件重新出现可恢复原笔记；未完成删除操作、来源删除或未解决冲突会阻止自动恢复。
- API／网页删除先记录持久删除任务，旧文件尚未清理时不会被误判为恢复。
- 根目录缺失、标记不匹配或扫描失败时暂停同步，不当成批量删除。

移动与编辑时保留完整 frontmatter；复制带同一 UUID 的文件会导致身份重复。如果想复制为新笔记，应对新副本移除 `id`，并确保其余协议有效。

### 10.3 两边同时改了怎么办

同步器比较“上次共同内容”、数据库现值和文件现值。单边改动自动同步；双方不同改动或编辑／删除冲突会保留双方快照并暂停自动覆盖。

到“同步与系统”打开冲突，确认正文、元数据、共同基线及删除状态，再选“选择系统版本”或“选择 Markdown 版本”，最后点击“使用所选版本”。这是选择一方，不是自动合并段落；选择已删除或文件缺失的一侧可能删除笔记。需要合并时先在外部保留双方内容，明确选择，再编辑最终笔记。

解决前任一方再次变化返回 409，重新读取新快照后再决定。普通编辑器与程序不共享写锁，系统保护已观测版本，不能承诺捕获两次扫描之间每次保存。

不要删除 `.memory-os-vault` 来“修复”错误；先核对数据库和完整知识目录是否配对。

<a id="rag"></a>
## 11. RAG 配置与启用

**完整步骤、可复制配置、桌面／Docker 地址区别、索引恢复和错误码：见 [RAG 配置指南](docs/rag-guide-cn.md)。**

### 当前电脑已接通的本地方案（2026-10-18）

固定桌面已启用 `local_bge_m3`：Ollama **0.40.6** 提供 `bge-m3` 的 **1024 维**向量，接口为 `http://127.0.0.1:11434/v1`，Qdrant **1.19.2** 为 `http://127.0.0.1:6333`。无需向量密钥；批次 1、超时 180 秒、分块 1200／重叠 200。当前 **2 篇知识笔记均已发布到索引**，两条改写查询及桌面重启后检索通过，571 篇资料仍只在资料库。

本次安装使用项目内官方免安装程序 `.tools/ollama/ollama.exe`；模型放在 `.cache/ollama/models/`。**桌面支持自动准备本地服务：配置后，直接双击原来的 `PersonalAiMemoryOs.exe` 即可，无需先执行 PowerShell 命令。** 程序隐藏启动／复用本项目的 Ollama，必要时启动 Docker Desktop，并仅启动 Compose 的 Qdrant 服务，就绪后打开工作台。不新增 Windows 开机启动项、不重新部署 API，也不会自动下载模型或调用 DeepSeek。

自动准备由 EXE 旁的 `config/local-rag-startup.json` 控制，示例见 [配置参考](docs/config-reference-cn.md#72-桌面本地服务自动准备)。**当前固定安装已配置并实测通过，日常不需要你再修改文件。** `project_root` 使用 `../..`，指向现有项目目录；通用新发行包默认不启用此配置，也不包含模型权重或 Docker。整体移动项目后需保持此相对关系；单独移走 EXE 目录后应重新核对项目位置。

启动诊断写入便携目录 `logs/local-rag-startup.log`，Ollama 日志仍在项目 `.cache/ollama/`。准备失败时可选择本次关闭 RAG、继续基础管理，磁盘配置不变；下次打开会重新尝试。关闭工作台保留共享的 Ollama 和 Qdrant，避免影响其他本地调用。`scripts/start_local_rag.ps1` 保留作手动排错入口。

桌面自动准备会为当前应用进程补齐 `NO_PROXY` 本机例外并保留已有项，避免系统代理转发本机请求；不依赖旧终端是否加载用户环境。更换模型权重时记录新的 digest/revision 并显式重建，不能只把同名模型覆盖。

现在可进入“搜索问答 → 语义检索”使用。引用问答复用现有 DeepSeek；**你主动提交后，问题与检索片段会发送给 DeepSeek，可能计费**。本次只验证本地检索，未执行真实生成问答，其质量仍待人工审阅。启用前已备份 SQLite、完整知识目录及配置，位置为便携目录内 `backups/upgrade-20261017-155556-24c86bbf/`。Qdrant 数据另在 Docker 命名卷中，不能只备份便携目录就当作完整向量备份。

### 11.1 必须准备什么

| 部分 | 作用 | 配置位置 |
| --- | --- | --- |
| Knowledge 笔记 | 被检索的内容 | 在工作台新建或采纳 |
| Embedding 服务 | 把笔记和查询转成浮点向量 | `config/embedding-providers.yml` |
| Qdrant | 存放和搜索向量 | `MEMORY_OS_RAG_QDRANT_URL` |
| 文本生成服务 | 将检索片段整理成带引用回答 | `config/ai-providers.yml`；只搜索时可不开启 |

Embedding 首版支持 `openai_embeddings` 协议，请确认服务真正提供 `/embeddings`，不是只提供聊天接口。应用不会因为你填了一个模型名而安装或启动该模型。

### 11.2 配好 Embedding

桌面推荐从左上角“设置”进入 **RAG 配置**：填写向量 profile 的地址、模型、真实维度、鉴权与密钥引用，选定默认 profile 和 Qdrant 地址。密钥留空保留已有值，保存只修改下次启动配置；需要生效时选择现在重启或稍后。

先保持 RAG 关闭完成接入。参数预检不发模型请求；“检测 Qdrant”只读取服务信息；“测试 Embedding”需要单独确认，发送一次短测试文本，可能计费但不建索引。配置就绪、连接通过与检索质量是不同状态。操作系统环境托管项和 Docker 只读规则继续生效。

启用并重启后会自动扫描全部合格笔记并向量化。更改模型、维度或模型 revision 后按页面提示显式重建。没有选定真实向量服务时保持关闭。以下文件示例用于需要手动配置的情况：

下面是格式示例，**模型名、地址、维度和密钥都要换成你实际服务的值，不能直接用占位符运行**：

```yaml
schema_version: 1
default_profile: embedding
profiles:
  embedding:
    label: 我的向量模型
    enabled: true
    protocol: openai_embeddings
    base_url: https://embedding.example.invalid/v1
    model: REPLACE_WITH_EMBEDDING_MODEL
    api_key_ref: embedding
    auth: bearer
    dimension: 1024
    batch_size: 8
    timeout_seconds: 60
```

`dimension` 必须是该模型实际返回维度，1024 不是通用值。支持降维的服务才配置 `request_dimensions`，且应与 `dimension` 相同。本地免密服务用 `auth: none` 并省略密钥引用。

编辑当前运行根目录的 `.env`，不要直接整文件覆盖掉已有 AI 密钥：

```dotenv
MEMORY_OS_EMBEDDING_CONFIG_FILE=config/embedding-providers.yml
MEMORY_OS_EMBEDDING_DEFAULT_PROFILE=embedding
MEMORY_OS_AI_KEYS__EMBEDDING=在本机填写向量服务密钥
MEMORY_OS_RAG_QDRANT_URL=http://127.0.0.1:6333
MEMORY_OS_RAG_ENABLED=true
```

生成和 Embedding 可以用不同服务、不同密钥。同一个 `api_key_ref` 表示共用密钥，默认模板中的 `local` 向量模型是占位配置，需替换后才可用。

### 11.3 启动 Qdrant 和应用

使用项目 Compose，在项目根目录启动：

```powershell
docker compose --profile rag up -d qdrant
```

桌面／本机 API 默认访问 `http://127.0.0.1:6333`；Compose 内 API 访问 `http://qdrant:6333`，这一项由 Compose 固定传入。容器访问宿主机 Embedding 时使用容器可达地址，例如 Docker Desktop 的 `host.docker.internal`，不能直接沿用 `127.0.0.1`。

便携目录没有 Compose 文件。只有 EXE 的用户可以运行指南中的独立 Qdrant 容器命令，或接入当前客户端兼容的既有 Qdrant 服务。当前客户端要求 Qdrant 1.19.x；Compose 固定 1.19.2，未提供 Qdrant API Key 配置，不能直接假定任意 Qdrant Cloud URL 都可使用。

准备好后，桌面完全退出重开；本机停止后重启；Compose 重新创建 API：

```powershell
docker compose up -d --force-recreate api
```

仅需语义搜索时，`MEMORY_OS_AI_ENABLED` 可以保持 `false`。需要问答时，再启用并配好文本生成 AI。

### 11.4 建立第一份索引并检查

1. 确认至少有一篇正常知识笔记，而不只是 Source。
2. 重启后打开“同步与系统”，查看 Embedding 配置和知识索引。
3. 开启 RAG 后每 5 秒自动对账，也可主动点击“更新索引”。
4. 等待已发布数量增加，确认没有失败项和异常排除。
5. 去“搜索问答”检索笔记中的一个具体主题。
6. 文本生成配置就绪时再测试引用问答。

打开 RAG 即可能自动调用 Embedding，不需要先点击索引按钮。查询本身也可能调用 Embedding。**“更新索引”不是完全免费的本地文件扫描按钮。**

模型、维度、显式 revision 或分块规则改变后，要“重建索引”，不是反复更新。失败／结果不明的向量调用需要明确“重试失败项”；普通后台扫描不自动重复它们。

<a id="search"></a>
## 12. 搜索与引用问答

### 12.1 语义检索

1. 进入“搜索问答”，选择语义检索标签。
2. 输入自然语言查询，选择“检索数量”（1—10，默认 5）。
3. 点击“搜索知识库”。
4. 查看片段、相似度、笔记版本、路径和关联来源；点击标题进入笔记。

“检索数量”指片段数，不是笔记数；同一笔记可能贡献多块。相似度不是答案正确率，也未设经过真实服务校准的固定分数门槛。

输入最多 2,000 字符。索引不完整时只展示当前有效片段并提示；索引不可用或服务故障不应被当作“知识库为空”。

### 12.2 引用问答

1. 选择引用问答标签，选择生成模型或使用默认模型。
2. 输入问题并主动生成。
3. 阅读回答段落的引用编号；点击编号查看对应原文摘录。
4. 点击引用笔记标题打开原笔记，也可查看关联 Source。

回答只依据本次检索知识；依据不足时明确说明。没有有效片段时不调用生成模型，但问答入口本身仍要求 AI 开关和配置就绪。

每段回答必须引用本次上下文，摘录必须存在于对应片段。虚构引用、无效摘录或结构错误返回失败，不自动修复重试。生成结束时再核验笔记，期间内容／有效状态变化可能返回 `409 context_changed`。

问答上下文最多 12,000 字符。当前是单轮问答，没有多轮会话和问答历史持久化；重要回答请自行整理为知识笔记。此处查询和回答不会自动新建笔记。

<a id="system"></a>
## 13. 同步与系统状态

### 13.1 Markdown 同步区

展示自动同步是否开启、后台任务是否运行、上次扫描、数量、文件问题和异常笔记。可点击“立即同步一轮”，但单次扫描不跳过稳定次数或删除宽限要求。

常见状态：

| 状态 | 意义 |
| --- | --- |
| `synced` | 数据库与文件共同基线已同步 |
| `pending` | 等待同步或文件操作 |
| `conflict` | 双方冲突，需人工处理 |
| `error` | 文件、权限、协议或身份问题 |
| `deleted` | 笔记已软删除 |

冲突区展示双方内容和删除状态。按 [第 10.3 节](#markdown)明确选择一方；旧快照过期时重新读取，不反复盲选。

### 13.2 知识索引区

| 操作 | 会做什么 |
| --- | --- |
| 更新索引 | 对账新／变更／删除笔记；必要时调用 Embedding，默认不重试失败项 |
| 重试失败项 | 显式允许重试失败、结果不明或中断的向量调用，可能再次计费 |
| 重建索引 | 新建代次；可能重新调用 Embedding，重建期间不保证检索可用 |

202／“任务已提交”不等于已经完成。观察发布数、待处理数、失败数、排除项和任务状态。

软删除、开放同步冲突或同步错误的笔记不可检索。单纯等待 Markdown 导出不阻止正常数据库内容索引；文件内部移动只更新引用路径，不应重新向量化。

成功向量先缓存在 SQLite，再写 Qdrant。Qdrant 恢复可以复用适用缓存；不要把删除数据库、反复重建或清理命名卷当成排错第一步。详见 [索引恢复](docs/rag-guide-cn.md)。

### 13.3 模型配置区

展示文本生成和 Embedding 的 profile、模型、维度、功能开关和配置状态。只读状态页不会探测远程接口或调用模型。进入“打开设置”，可分别编辑文本生成和 RAG 配置；连接测试是单独的主动操作。

`/health` 仅维持数据库健康检查合同。健康正常不等于 Qdrant、Embedding 或生成模型可用。

<a id="backup"></a>
## 14. 备份、恢复、升级与搬迁

### 14.1 应备份什么

最省心的桌面备份是：正常退出后复制**整个便携目录**。

最小成对数据包括：

- 当前 SQLite 文件（默认 `data/memory.db`，内有 Source、Knowledge、草稿、同步和向量缓存）。
- 完整 `knowledge/`，包括隐藏的 `.memory-os-vault`。
- `.env` 和个人 `config/`，含开关和凭据；受保护保存。
- 使用自定义路径时，对应目录也要备份。

仅复制 Markdown 会漏掉资料、草稿、来源关系、版本、同步身份和缓存。仅复制数据库也会缺失配套文件与身份标记。

Qdrant 命名卷是单独存储，不包含在文件夹复制中。可按服务的快照／备份方式保存；丢失后部分索引可由成功向量缓存恢复，不能承诺所有重建都无需远程调用。

### 14.2 项目默认目录的手动备份

先关闭桌面或 `Ctrl+C` 退出本机服务；使用同一项目库的 Compose API 也应停止。下列命令不会删除原文件：

```powershell
docker compose stop api
$backupPath = Join-Path $PWD ('data/backups/manual-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backupPath | Out-Null
Copy-Item -LiteralPath data/memory.db -Destination (Join-Path $backupPath 'memory.db')
Copy-Item -LiteralPath knowledge -Destination (Join-Path $backupPath 'knowledge') -Recurse -Force
Copy-Item -LiteralPath .env -Destination (Join-Path $backupPath '.env')
Copy-Item -LiteralPath config -Destination (Join-Path $backupPath 'config') -Recurse -Force
```

没有使用 Docker 时可省略第一行。示例只适用于默认路径且文件存在的库；自定义路径请备份实际位置。不要公开包含 `.env` 的备份。

### 14.3 升级便携 EXE

本项目桌面安装固定为 `dist/PersonalAiMemoryOs-0.6.6/`，**以后不新建版本安装目录**。目录名保留历史名称，当前版本为 0.8.0。

最近的自动启动补丁已完成该目录的备份、原地升级和重新打开；当时核验的 571 篇资料、2 篇笔记、3 条运行记录、1 个批次，以及全部知识文件和模型配置均已保留。该次备份位于 `backups/upgrade-20261017-162717-811af92d/`；更早的 `152603` 备份属于最初 0.8.0 升级，内容以各自时点为准，完整验收见[工程任务记录](IMPLEMENTATION_TASKS.md)。

1. 在 `.cache` 中完成干净构建与隔离 EXE 验收，发行 ZIP 也从干净产物生成。
2. 正常关闭当前程序，等待在途调用和同步结束；运行中升级器会拒绝替换。
3. 升级器先备份并核验 SQLite、完整知识目录、`.env` 和配置，再备份旧程序资源。
4. 原地替换清单中已纳管的程序文件；保留个人数据、日志、导出和未知文件。自定义路径与程序资源重叠或未知文件冲突时停止。
5. 执行支持版本到 `0006` 的迁移，核验全部旧记录，再从原目录启动并检查资料、笔记和设置。旧模板归入笔记解析，问答另有独立默认项；不要只换网页或 EXE。

开发维护命令（先关闭 EXE，`--bundle` 填本轮验收通过的干净构建路径）：

```powershell
uv run --locked python scripts/build_desktop.py --staging-only
uv run --locked python scripts/update_desktop.py --bundle .cache/desktop-build/本轮编号/dist/PersonalAiMemoryOs
```

旧安装无资源清单时，需保留原始 `PersonalAiMemoryOs-0.6.6-windows-x64.zip` 确认哪些旧文件属于程序。备份在安装目录 `backups/upgrade-.../`，含私人配置，请勿公开。程序备份采用 `program/000000.bin` 等短文件名，原路径与备份对应关系记录在 `program-update.json` 的 `path`／`backup` 字段，避免 Windows 长路径限制。升级若留下 `.memory-os-upgrade.json`，新程序会停止启动；核对该记录、清单和备份后恢复，不要直接删标记绕过半完成检查。

新安装可解压干净 ZIP；不要将干净包直接整体覆盖运行中的安装。普通源码／Docker 仍手动备份后执行 `uv run --locked alembic upgrade head`。未知／高于支持版本／结构不完整的数据库拒绝启动。

### 14.4 恢复和整体移动

停服后将数据库和完整知识目录成对恢复，使用匹配版本程序。不要把新数据库与另一个库的标记随意拼接，也不要手工修改标记绕过检查。

默认相对路径随整个便携目录移动而工作；如果自己填过指向旧位置的绝对路径，需要在新目录内改为正确的相对／绝对路径，不能指向便携目录外。

模型和 Qdrant 是外部服务，搬动便携目录不会同时搬走它们。另一台机器的服务地址、网络和 WebView2 运行环境需要重新核对。

完整恢复演练的停机、清单校验、成对数据、配置、同步身份和独立 Qdrant 检查见 [隔离恢复演练清单](docs/project-audit-cn.md#recovery)。现有备份和升级回滚已经实现；完整演练仍是待验收事项，不要在正式库上直接试恢复。

### 14.5 空间、日志与运行边界

同一份 SQLite 和知识目录只由一个应用进程维护，源码／Docker／桌面不要并行共用；Uvicorn 保持一个 worker。复制完整库而共享同一 Qdrant owner 时，也不要把两份同时运行当作隔离方案。

普通 `memory-os.log` 已轮转；本地服务启动日志、Ollama 输出、旧构建／验收和备份的保留策略仍待完善。`.cache/ollama/models/` 保存真实模型权重，不能把整个 `.cache` 当作可随便清空的临时目录。当前本轮未清理任何文件，建议先按 [维护清单](docs/project-audit-cn.md#storage) 分类确认用途和占用。

<a id="api"></a>
## 15. Swagger、API 与辅助命令

### 15.1 常用 API 分组

在 Swagger 的“Try it out”填写实际 UUID 和版本；下表提供索引，完整字段以当前 `/openapi.json` 为准。

| 接口组 | 常用接口／用途 |
| --- | --- |
| 健康 | `GET /health` |
| 原始资料 | `/api/v1/sources` 的创建／列表，`/{id}` 的详情／修改／软删除，`/{id}/restore` |
| 知识笔记 | `/api/v1/knowledge` 及详情／修改／软删除／恢复 |
| 网页摘要与分组 | `/api/v1/ui/overview`、`/sources`、`/knowledge`、`/drafts`、`/source-groups`、`/source-groups/items` |
| 知乎导入 | `POST /api/v1/imports/zhihu`、`/zhihu-markdown`，`?dry_run=true` 预演 |
| 文本模型 | `GET /api/v1/ai/profiles` |
| 草稿运行 | `POST/GET /api/v1/processing/runs`、`GET /{id}`、`POST /{id}/adopt` |
| 持久生成任务 | `POST/GET /api/v1/processing/batches`、`GET /{id}`、`GET /{id}/items`、`GET /{id}/items/{item_id}/attempts`、`POST /{id}/continue`、`/retry-failed`、`/cancel` |
| 提示词模板 | `/api/v1/prompt-templates?purpose=knowledge` 或 `purpose=rag_qa`、`/{id}`、`/{id}/revisions`、`/{id}/revisions/{version}`、`/{id}/default`、`/{id}/archive` |
| 同步 | `GET /api/v1/sync/status`、`POST /api/v1/sync/run`、`GET /api/v1/sync/conflicts`、`GET /api/v1/sync/conflicts/{id}`、`POST /api/v1/sync/conflicts/{id}/resolve` |
| RAG | `GET /api/v1/rag/embedding-profiles`、`/index/status`；`POST /index/run`、`/index/rebuild`、`/search`、`/ask` |
| AI 设置 | `GET/PUT /api/v1/settings/ai`，本机同源与令牌保护 |
| RAG 设置 | `GET/PUT /api/v1/settings/rag`；显式 `POST /api/v1/settings/rag/test` 检查 Qdrant 或确认后测试 Embedding |
| 分页系统明细 | `/api/v1/sync/notes`、`/sync/issues`、`/rag/index/errors`、`/rag/index/excluded`，均位于 `/api/v1` 下 |
| 桌面重启 | `POST /api/v1/desktop/restart`，仅 EXE 启用；校验 Origin、配置令牌及 revision，可指定 `scope: "ai"` 或 `"rag"` |

Source／Knowledge 修改请求 JSON 包含 `expected_version`；DELETE 使用查询参数 `?expected_version=N`；恢复在 JSON 中提交版本。生成提交 `expected_source_version`，采纳提交草稿的 `expected_version`；同步冲突解决提交 `{"choice":"database"}` 或 `{"choice":"markdown"}`，设置写入使用 `expected_revision`。版本来自刚读取的记录，不要硬编码 1 或在冲突后直接加一。

Knowledge 可提交有序 `source_ids`（最多 20 个），`source_id` 保留首项兼容字段；两者同时提供须一致。设置写入与桌面重启需要同源 Origin 和本进程配置令牌。日常使用设置页；直接调用时遵循当前接口安全要求，不能把 403 当作服务器坏了。

列表使用 `offset`／`limit`；网页统一提供 10／20／50／100 条每页，默认 20。摘要接口以及运行、批次、状态和模板的 `summary_only=true` 用于轻量列表；完整详情按需另取。RAG 问答可提交 `prompt_template_id` 和 `prompt_template_version`，只能选 `rag_qa` 用途；省略时使用该用途的默认模板。分页只读取已经取得的结果，不重新导入或调用模型。

### 15.2 本地 JSON 导入命令

在项目根目录、已经启动 API 的前提下：

```powershell
uv run --locked python scripts/import_zhihu.py --file examples/zhihu-import.sample.json --dry-run
uv run --locked python scripts/import_zhihu.py --file imports/my-zhihu.json --dry-run
uv run --locked python scripts/import_zhihu.py --file imports/my-zhihu.json
```

默认 API 是 `http://127.0.0.1:18000`，可用 `--base-url` 指定。CLI 文件需位于项目内，报告放 `.cache/import-reports/`；有无效项或请求失败时退出非零。网页选择文件不受 CLI 项目路径要求限制。

### 15.3 开发检查与真实验收

普通用户无需运行测试或安装浏览器来使用 EXE。开发者命令：

```powershell
uv sync --locked
uv run --locked pytest
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD '.cache/playwright'
uv run --locked playwright install chromium
docker build -t memory-os-v08-validation .
uv run --locked python scripts/verify_v08_rag.py --mode all --image memory-os-v08-validation
uv run --locked python scripts/verify_v08_web.py --mode local
uv run --locked python scripts/verify_v08_web.py --mode docker --image memory-os-v08-validation
# EXE 验收使用干净构建目录，不使用已含个人数据的安装目录。
uv run --locked python scripts/build_desktop.py --staging-only
uv run --locked python scripts/verify_desktop.py --bundle .cache/desktop-build/本轮编号/dist/PersonalAiMemoryOs
uv run --locked python scripts/verify_v08_web.py --mode desktop --bundle .cache/desktop-build/本轮编号/dist/PersonalAiMemoryOs
uv run --locked python scripts/verify_desktop_upgrade.py --bundle .cache/desktop-build/本轮编号/dist/PersonalAiMemoryOs
```

综合验收使用隔离模型和真实隔离 Qdrant，需要 Docker。缓存、截图和测试资料放在 `.cache/`，生产镜像不带测试浏览器。

真实 EXE 验收按顺序运行，避免同时操作多个测试窗口。旧版本布局专用脚本保留为历史证据，当前页面使用 `verify_v08_web.py`；问答页面传输和分页的受控模拟测试，与真实 Qdrant 的 HTTP 集成验收分别记录。

`scripts/verify_real_provider.py --check` 仅做配置预检；`--run` 才执行真实调用。该专用第四阶段验收曾设定最多三次调用的预算，不是应用日常生成次数上限，也不自动给 Embedding／问答真实验收授权或增加预算。

构建 Windows 便携包的命令见 [English README](README.md)；构建与运行是两件事，日常不必重新打包。

<a id="troubleshooting"></a>
## 16. 常见问题与排错顺序

### 16.1 先确认你打开了哪个库

先看版本和“设置”中的运行目录，再查当前服务日志。桌面随机端口和项目 18000 可能是两个完全不同的数据库；不同便携目录也不会自动共享资料。

| 现象 | 原因与处理 |
| --- | --- |
| 新版打开没有旧资料 | 新目录首次为空库；按升级步骤复制配套数据，不要在旧程序运行时复制 |
| 18000 的网页没有新版设置入口 | 可能仍是旧 Docker／本机部署；EXE 升级不会自动升级该服务 |
| 同标题少了很多行 | 列表按标题分组；进组看各篇回答，记录没有合并 |
| “类型”排序没变化 | Source 类型可能全部是 `zhihu`；回答／文章／想法不是该排序字段 |
| 导入后搜索不到 | 导入的是 Source；先有 Knowledge，再启用并建立 RAG 索引 |
| 配了 DeepSeek 仍不能搜索 | 还需要独立 Embedding 和 Qdrant；文本生成不是向量化服务 |
| AI／搜索按钮灰色 | 查看开关、来源、所选模型及配置就绪状态；修改文件后重启 |
| 设置保存了但仍显示旧模型 | 保存的是下次启动配置；在 EXE 选择“现在重启”或彻底退出重开，不是只刷新网页 |
| 批次暂停／中断 | 查看逐项错误，先确认来源／模型配置；继续待处理与重试失败分别确认，不会自动重发 |
| 深度分析截断 | 查看结束原因与用量，核对输出预算和思考模式；主动新建／重试才会再调用，未采纳不会产生笔记 |
| 密钥框一直是空的 | 有意不回显；看“已配置”，留空会保留旧值 |
| 模型显示就绪但认证失败 | 就绪不探测真实服务；核对 Key、地址、模型权限、供应商余额及日志 |
| 修改 `.env` 没生效 | 检查是否改了另一个库、被环境覆盖，或容器未重新创建 |
| Docker 新增模型总缺密钥 | 自定义引用尚未在 Compose 显式传入；按配置参考添加透传 |
| 容器访问宿主机模型失败 | 容器的 localhost 指向自身；用其可达地址／`host.docker.internal` |
| Qdrant 有 API Key 却无法连接 | 当前客户端没有 Qdrant Key 配置，不能直接接需要该头的端点 |
| RAG 开启但索引没有完成 | 看失败／排除／pending 状态和配置，不只看 `/health` |
| 搜索能用但问答不能用 | 搜索不要求生成 AI；问答还需开启且配置文本模型 |
| 搜索数量与笔记数量不同 | 数量是片段数，同一篇笔记可能命中多个片段 |
| 结果提示“索引不完整” | 尚有待处理或失败项；当前结果只用已发布有效片段 |
| 模型／维度改了更新无效 | 配置不兼容需显式重建新代次；先重启加载新配置 |
| 文件保存后没有立即回写 | 需两次稳定扫描；确认同步开启，去系统页查看文件问题 |
| 提示目录标记不匹配 | 数据库和知识目录可能不配对；恢复配套备份，不删标记绕过 |
| 来源无法删除 | 尚有正常关联笔记；先处理或解除关联 |
| 笔记无法恢复 | 查看来源是否被删、路径是否占用、未完成操作及开放冲突 |
| 采纳按钮不可用 | 草稿失败／未完成，或来源版本已变／删除；基于最新来源生成 |
| 关闭窗口一直等待 | 有在途调用或同步任务；程序等待正常结束，避免强制终止 |

### 16.2 按 HTTP 状态排查

| 状态 | 常见含义 | 下一步 |
| --- | --- | --- |
| 400／422 | JSON、YAML、字段、协议、长度或 profile 无效 | 对照提示和配置参考修改，不反复原样提交 |
| 403 | 设置接口访问方式或令牌不符 | 通过本机设置页重新读取；不要去掉保护 |
| 404 | UUID 不存在、已删除或当前入口不包含回收站 | 确认库、记录 ID 和回收站状态 |
| 409 | 版本／来源／同步快照过期、功能禁用或配置不兼容 | 按具体错误重新读取、解决冲突或重建 |
| 413 | 导入／设置请求体超限 | 减少单批，保留原文，不截断后假装成功 |
| 429 | 模型或索引相关操作忙 | 等待当前任务，之后主动操作 |
| 502 | 上游响应或生成／向量结果不合要求 | 查运行／索引错误；无效结果不会自动修复重试 |
| 503 | 数据库、配置、索引或服务不可用 | 查实际错误码、日志和连通性 |
| 504 | 模型／远程调用超时 | 先查询已有运行／任务，避免重复收费调用 |

真实错误以响应 `detail.code`／运行记录为准；不是每个接口都会使用表内全部状态。

### 16.3 去哪里看日志

- 桌面：“工作空间 → 查看日志”，默认 `logs/memory-os.log`，每份约 2 MiB、最多 3 份轮转备份。
- 本机 Python：启动终端。
- Docker：`docker compose logs --tail 100 api`；Qdrant 则查 `qdrant` 服务日志。
- 准备反馈时说明版本、运行方式、操作、错误码和时间；先移除密钥及私人正文。

配置事务恢复冲突时，不随意删除恢复目录或临时文件。先备份当前配置和恢复记录，按日志定位，避免把两份配置的半完成状态当成已成功保存。

<a id="limits"></a>
## 17. 字段限制、未实现功能与工程记录

### 17.1 常用字段上限

| 内容 | 约束 |
| --- | --- |
| 标题 | 去首尾空白，1—500 字符 |
| Source 来源类型 | 1—50 字符，手工默认 `manual` |
| 作者／原文链接 | 最多 200／4,096 字符 |
| Source 正文／笔记正文 | 最多 2,000,000 字符；手工正文可为空 |
| 摘要／分类 | 最多 100,000／200 字符；分类可空 |
| 标签／概念 | 各最多 100 项，每项去首尾空白后 1—100 字符 |
| 网页正文预览 | 超过 100,000 字符暂停，编辑保存仍保留完整内容 |
| 草稿默认输入 | Source 正文 20,000 字符，可配置 |
| 批次与多来源 | 每批 1–20 篇；逐篇各自校验输入，合并累计正文；每笔记最多 20 来源 |
| 深度模板默认参数 | 16,384 输出 tokens、180 秒；可分别修改为 1–131,072／0.01–600 秒范围内的合法值，以实际接口校验为准 |
| AI 核心要点／观点 | 各最多 20 条；要点、观点和证据每项最多 2,000 字符，分析 4,000 |
| 搜索／问题长度 | 最多 2,000 字符；片段数默认 5、最大 10 |
| RAG 默认分块 | 1,200 字符，重叠 200；单篇组合文本最多 100,000 字符、200 块 |
| 问答上下文 | 最多 12,000 字符 |

字符限制不等同于供应商 token 限制。标题、摘要等也参与检索文本组合，正文不足 100,000 不保证组合后一定未超限。

### 17.2 当前没有的能力

- 知乎在线登录、自动同步收藏、抓取正文或下载图片。
- 无人确认自动生成／自动采纳、自动重发失败的付费调用。
- 独立 Opinion 管理、资料记录自动合并、拼音排序。
- 多用户、账号权限、云 IAM 鉴权、互联网公开部署方案。
- 多轮聊天、问答历史、混合检索、重排序。
- 自动更新、安装器、数字签名和跨电脑兼容保证。
- 自动把另一个安装目录的资料迁入当前库。

### 17.3 版本和验收边界

0.8.0 发布时的最终全量回归为 **1,088 项测试通过、3 项 Windows 符号链接权限跳过、1 条已有上游警告**（`.cache/v08/pytest-release.log`）。本机和 Docker 浏览器、实际打包 EXE、新旧库原地升级均通过验收，覆盖独立 Prompt／草稿页面、所有分页尺寸、配置跨页保存、旧响应保护及真实重启交接。当时的模型均为本地模拟；发布默认 RAG 关闭。后续本机接入未修改应用版本、数据库结构或发行包，新增 16 项工具安全测试通过；真实 BGE-M3 隔离验收及当前桌面两篇笔记检索、重启验证已通过。

桌面自动准备补丁的完整回归为 **1,135 项通过、3 项 Windows 符号链接权限跳过、1 条已有警告**；新包实际 EXE 基础操作、服务复用、系统代理下本机连接、重复双击及受保护重启均通过。已在原目录备份并更新，备份位于 `backups/upgrade-20261017-162717-811af92d/`，571 篇资料、2 篇笔记、既有配置和全部知识文件均已核验保留；自动准备及本次升级未发起模型调用。

最新干净发行包为 `dist/PersonalAiMemoryOs-windows-x64.zip`，SHA-256：`a20ce7ba7e358807a9ce616f5c8b1997ae6b85fa8d0e18eed0b8cdd7aba9cd23`；EXE 为 `6ccffca5855bc689c9b121e0b488cd70f7a572df3cd30fa3413cd245b3f59535`。Windows 长路径升级问题已修复并复验，旧数据、模板和完整知识文件均有核验备份。详细证据见[工程任务记录](IMPLEMENTATION_TASKS.md)。上版 0.7.0 的 1,030 项回归及历史交付记录继续保留。

第四阶段真实 DeepSeek 生成质量、第五阶段完整引用问答质量仍待单独验收；本地 Embedding 接口与少量检索样例通过不等于所有问题都能准确回答。生产原生“另存为”交互及第二台干净电脑也保留单独验证边界。工程验收和日常功能开关是不同概念，不需要每次使用都重新执行工程验收脚本。

详细历史发布、校验值和当时部署记录移至 [0.6.6 及之前的说明归档](docs/readme-cn-0.6.6-archive.md)。当前实际运行版本／数据数量以你打开的应用为准。

<a id="documents"></a>
## 18. 其他文档

| 文档 | 用途 |
| --- | --- |
| [RAG 配置指南](docs/rag-guide-cn.md) | 从零准备向量服务、Qdrant、索引和搜索问答 |
| [完整配置参考](docs/config-reference-cn.md) | 全部环境变量、文本／向量 profile 字段、默认值和限制 |
| [English README](README.md) | 英文介绍、构建与验证命令 |
| [SPEC.md](SPEC.md) | 产品目标与范围 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构和分层 |
| [DATABASE_DESIGN.md](DATABASE_DESIGN.md) | 数据模型与迁移 |
| [ROADMAP.md](ROADMAP.md) | 后续阶段与真实验收状态 |
| [IMPLEMENTATION_TASKS.md](IMPLEMENTATION_TASKS.md) | 已执行任务和验收证据 |
| [MEMORY.md](MEMORY.md) | 长期工程决策 |
| [AGENTS.md](AGENTS.md) | 项目协作约定 |

说明书核对日期：2026-10-17。以当前源码、配置类型和隔离验收核对；历史部署记录不代表已开启真实模型或 RAG。
