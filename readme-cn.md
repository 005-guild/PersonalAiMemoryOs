# Personal AI Memory OS — 完整中文使用手册

[English README](README.md) · [RAG 配置指南](docs/rag-guide-cn.md) · [全部配置参数](docs/config-reference-cn.md)

适用版本：**0.6.6**；数据库版本：**0004**。本文介绍已实现的功能和操作，不代表已替你启用模型、搬迁资料或更新正在运行的服务。

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
| 生成、检查并采纳知识草稿 | [9. AI 草稿](#drafts) |
| 用外部编辑器维护 Markdown | [10. Markdown 同步](#markdown) |
| 开启 RAG，需要哪些服务、怎么填 | [11. RAG 配置与启用](#rag)、[逐步配置指南](docs/rag-guide-cn.md) |
| 搜索、提问、阅读引用 | [12. 搜索与问答](#search) |
| 处理同步冲突和索引错误 | [13. 同步与系统状态](#system)、[16. 排错](#troubleshooting) |
| 换电脑、升级 EXE、备份恢复 | [14. 备份、恢复与升级](#backup) |
| 用脚本或 Swagger 调用接口 | [15. 接口与命令](#api) |
| 查所有环境变量与 YAML 字段 | [完整配置参考](docs/config-reference-cn.md) |
| 查功能限制与验收范围 | [17. 限制与工程记录](#limits) |

<a id="basics"></a>
## 1. 功能与基本概念

### 1.1 三种内容分别是什么

| 名称 | 保存什么 | 从哪里产生 | 是否进入 RAG |
| --- | --- | --- | --- |
| 资料 Source | 原文、标题、作者、原文链接和来源类型 | 手工新建、知乎 JSON／Markdown 导入 | 不直接进入 |
| 草稿 Processing Run | 某次 AI 调用的来源快照、结构化结果、笔记预览和用量 | 主动点击“生成知识草稿” | 不进入 |
| 知识笔记 Knowledge | 可以长期编辑的标题、摘要、分类、标签、概念和 Markdown 正文 | 手工创建、符合协议的外部 Markdown、采纳草稿 | 启用 RAG 后按条件索引 |

一份资料可以关联多篇笔记；笔记也可以没有资料来源。**导入 571 篇资料不等于生成了 571 篇知识笔记**。相同标题显示成一组，只改变资料列表的展示，不合并原始记录。

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

1. 完整解压 `dist/PersonalAiMemoryOs-0.6.6-windows-x64.zip` 到可写目录。
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

所有运行配置在启动时加载。网页保存、外部编辑 YAML 或 `.env` 后都需重启；刷新网页不会重新加载后端配置。

Compose 只传入 `environment:` 中显式列出的变量。宿主机 `.env` 有一个值，不代表该值已经进入容器。目录、开关和高级参数的完整对照见 [配置参考](docs/config-reference-cn.md)。

<a id="navigation"></a>
## 4. 工作台导航与通用操作

| 页面 | Hash 路由 | 用途 |
| --- | --- | --- |
| 设置 | `#/settings` | 编辑 AI 配置、查看运行和存储位置 |
| 概览 | `#/` | 查看实际数量、状态和常用入口 |
| 资料库 | `#/sources` | 同标题分组、分页排序、查看和维护各条资料 |
| 资料导入 | `#/imports` | 知乎 Markdown／JSON 预演、提交和报告 |
| 知识笔记 | `#/knowledge` | 新建、编辑、预览、批量软删除和恢复笔记 |
| AI 草稿 | `#/processing` | 生成、筛选运行记录、查看和采纳 |
| 搜索问答 | `#/search` | 语义搜索和单轮引用问答 |
| 同步与系统 | `#/system` | 同步、冲突、索引任务和配置就绪状态 |

右上“API 文档”打开 Swagger。窄屏导航可以收起，顶部也有直接设置入口。列表和详情在同一工作台中切换，刷新 Hash 详情路由仍可定位。

通用规则：

- 修改、删除、恢复使用读取时的版本号。409 表示内容或状态已变化，保留当前输入并比较最新版本，不能盲目覆盖。
- 未保存修改时，切换记录、离开页面或关窗会提示。后台轮询不覆盖编辑框。
- “数据库已保存”不等于“Markdown 已同步”；保存后可在同步状态中确认。
- 生成、问答和索引维护按钮不会自动重复提交；失败不自动重试模型。
- 普通文本按文本显示，Markdown 经安全清洗；外部图片不自动加载，原始 HTML 不执行。
- 支持常规键盘 Tab、Enter 和页面中的按钮操作。不要假定存在未标出的快捷保存或批量生成功能。

概览的“原始资料”统计正常 Source 条数，不是资料库标题组数。“待采纳草稿”统计 ready 记录，其中可能有因来源过期而不能采纳的草稿。概览还展示最近 5 篇笔记和常用入口；进入具体记录确认可用状态。

<a id="sources"></a>
## 5. 资料库：分页、同标题分组、排序与回收站

### 5.1 浏览和查找

1. 打开“资料库”，输入标题关键词。匹配标题中的字面包含内容，不是语义搜索。
2. 选择“正常／回收站／全部”。
3. 选择排序项：标题、资料数量、来源类型、更新时间；可选升序／降序，也可点击列标题。
4. 选择每页 20／50／100 个标题；点击数字页码，或输入页码跳转。

筛选后先按**完全相同的标题**分组，排序整个结果，再分页。默认更新时间降序；切换排序回到第一页。列表页数按标题组计算，不按原始回答总数计算。

标题和类型按数据库字符顺序排序，不是中文拼音。类型排序使用 `Source.source_type`（例如 `zhihu`、`manual`），不是回答／文章／想法；全是知乎资料时这项通常相同。混合类型组按当前可见成员中字符顺序最前的来源类型排序。

### 5.2 同题下有多篇回答

点击标题进入组内，分别查看每条资料的作者、原文链接和完整内容。组内每页 5／10／20 篇。可以针对某一条编辑、生成草稿或查看关联笔记和处理记录。

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
4. 保存，确认数据库已保存；等待 Markdown 同步完成。

分类是自由文字，例如“数据库／工程实践”，不是固定分类树。网页标签和概念按中文逗号、英文逗号或换行分隔并去重；需要把逗号作为单个标签内容时，不宜用该网页输入方式重新编辑。

笔记列表可按标题、来源和“正常／回收站／全部”筛选。笔记页目前固定每页 20 条，使用上一页／下一页；资料库的数字跳页、每页条数和四种排序不适用于此页。

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
7. 保存后**完全退出并重开**。

新建模板不会联网探测，也不会自动开启。配置 ID 是小写字母开头、最多 64 字符的标识；它与供应商模型 ID 是两个字段。

密码框留空保留已有值；只有填写新值才替换密钥。多个 profile 共用同一密钥引用时，替换会影响它们。删除 profile 不删除本机保存的密钥。

保存不调用模型、不热加载、不自动重启，也不启用 RAG。“配置就绪”只表示参数和所需密钥齐全，不表示认证、余额、接口连通或生成质量已经验证。

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
## 9. AI 草稿：生成、查看与采纳

1. 在资料详情选择生成草稿，或去“AI 草稿”查找一条正常来源。
2. 选择就绪模型；留默认项时使用默认 profile。
3. 主动点击“生成知识草稿”，等待结果。
4. 查看笔记预览、摘要、分类、核心要点、原文观点、依据和 AI 分析。
5. 核对来源快照和原文，确认后“采纳为新笔记”。
6. 进入新笔记编辑，按自己的理解修订，再等待 Markdown 导出。

**生成和预览不会创建知识笔记或 Markdown。** 采纳才产生新 Knowledge。重复或并发采纳同一草稿返回原笔记，不重复创建。

| 状态 | 含义与下一步 |
| --- | --- |
| `running` | 模型调用中，查询现有记录，避免重复提交 |
| `ready` | 已生成、待审阅；来源未过期才能采纳 |
| `adopted` | 已采纳，可打开对应笔记 |
| `failed` | 调用或结果验证失败，查看错误后自行决定是否新建调用 |
| `interrupted` | 启动时发现上次未完成的调用，不会自动重新调用 |

Source 任意版本变化或软删除都可能让草稿过期；不是只有正文变化才过期。需基于最新 Source 重新生成，旧结果保留以便查看。

模型输出必须满足结构和原文依据验证；无效 JSON、空摘要、截断、拒答或无效依据会失败，不创建笔记。观点以“原文观点／依据／AI 分析”分开写入笔记。

默认正文输入最多 20,000 字符，超长明确拒绝，不自动截尾或分批。草稿与问答共享一个文本生成并发名额，繁忙返回 429。模型调用在锁和长数据库事务外，普通资料管理不必等待模型完成。

来源／状态／模型可用于筛选处理记录，记录每页 20 条。断连或客户端超时后，先在该来源记录中找结果，避免重复产生调用。启动时恢复“中断”状态，不自动重试。

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

### 11.1 必须准备什么

| 部分 | 作用 | 配置位置 |
| --- | --- | --- |
| Knowledge 笔记 | 被检索的内容 | 在工作台新建或采纳 |
| Embedding 服务 | 把笔记和查询转成浮点向量 | `config/embedding-providers.yml` |
| Qdrant | 存放和搜索向量 | `MEMORY_OS_RAG_QDRANT_URL` |
| 文本生成服务 | 将检索片段整理成带引用回答 | `config/ai-providers.yml`；只搜索时可不开启 |

Embedding 首版支持 `openai_embeddings` 协议，请确认服务真正提供 `/embeddings`，不是只提供聊天接口。应用不会因为你填了一个模型名而安装或启动该模型。

### 11.2 配好 Embedding

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

展示文本生成和 Embedding 的 profile、模型、维度、功能开关和配置状态。只读状态页不会探测远程接口或调用模型。文本生成的编辑入口是“打开设置”，RAG 参数仍编辑文件。

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

1. 正常关闭旧程序，确认其任务结束。
2. 备份完整旧目录。
3. 解压新版完整包到另一个新目录，不覆盖运行中的安装。
4. 在新版首次运行前，复制旧的 `.env`、`config/`、`data/` 和完整 `knowledge/`；自定义的目录内路径也要保留。
5. 打开新版，检查资料数量、笔记、同步和配置状态。

从 0.6.3—0.6.6 升级仍为数据库 `0004`，无需新迁移，但必须使用完整程序，不能只换网页或 EXE。更旧支持版本需要迁移时，桌面会先提示并备份；未知／高于支持版本／结构不完整时拒绝启动。

### 14.4 恢复和整体移动

停服后将数据库和完整知识目录成对恢复，使用匹配版本程序。不要把新数据库与另一个库的标记随意拼接，也不要手工修改标记绕过检查。

默认相对路径随整个便携目录移动而工作；如果自己填过指向旧位置的绝对路径，需要在新目录内改为正确的相对／绝对路径，不能指向便携目录外。

模型和 Qdrant 是外部服务，搬动便携目录不会同时搬走它们。另一台机器的服务地址、网络和 WebView2 运行环境需要重新核对。

<a id="api"></a>
## 15. Swagger、API 与辅助命令

### 15.1 常用 API 分组

在 Swagger 的“Try it out”填写实际 UUID 和版本；下表提供索引，完整字段以当前 `/openapi.json` 为准。

| 接口组 | 常用接口／用途 |
| --- | --- |
| 健康 | `GET /health` |
| 原始资料 | `/api/v1/sources` 的创建／列表，`/{id}` 的详情／修改／软删除，`/{id}/restore` |
| 知识笔记 | `/api/v1/knowledge` 及详情／修改／软删除／恢复 |
| 网页摘要与分组 | `/api/v1/ui/overview`、`/sources`、`/knowledge`、`/source-groups`、`/source-groups/items` |
| 知乎导入 | `POST /api/v1/imports/zhihu`、`/zhihu-markdown`，`?dry_run=true` 预演 |
| 文本模型 | `GET /api/v1/ai/profiles` |
| 草稿运行 | `POST/GET /api/v1/processing/runs`、`GET /{id}`、`POST /{id}/adopt` |
| 同步 | `GET /api/v1/sync/status`、`POST /api/v1/sync/run`、`GET /api/v1/sync/conflicts`、`GET /api/v1/sync/conflicts/{id}`、`POST /api/v1/sync/conflicts/{id}/resolve` |
| RAG | `GET /api/v1/rag/embedding-profiles`、`/index/status`；`POST /index/run`、`/index/rebuild`、`/search`、`/ask` |
| AI 设置 | `GET/PUT /api/v1/settings/ai`，本机同源与令牌保护 |

Source／Knowledge 修改请求 JSON 包含 `expected_version`；DELETE 使用查询参数 `?expected_version=N`；恢复在 JSON 中提交版本。生成提交 `expected_source_version`，采纳提交草稿的 `expected_version`；同步冲突解决提交 `{"choice":"database"}` 或 `{"choice":"markdown"}`，设置写入使用 `expected_revision`。版本来自刚读取的记录，不要硬编码 1 或在冲突后直接加一。

设置写入不是普通无保护 PUT，需要同源 Origin 和本进程配置令牌。日常使用设置页；直接调用时遵循当前接口安全要求，不能把 403 当作服务器坏了。

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
uv run --locked python scripts/v06_acceptance.py --mode all
uv run --locked python scripts/verify_settings_ui.py
uv run --locked python scripts/verify_ai_settings.py --bundle dist/PersonalAiMemoryOs-0.6.6
```

综合验收使用隔离模型和真实隔离 Qdrant，需要 Docker。缓存、截图和测试资料放在 `.cache/`，生产镜像不带测试浏览器。

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
| 设置保存了但仍显示旧模型 | 保存的是下次启动配置；彻底退出重开，不是只刷新网页 |
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
| AI 核心要点／观点 | 各最多 20 条；要点、观点和证据每项最多 2,000 字符，分析 4,000 |
| 搜索／问题长度 | 最多 2,000 字符；片段数默认 5、最大 10 |
| RAG 默认分块 | 1,200 字符，重叠 200；单篇组合文本最多 100,000 字符、200 块 |
| 问答上下文 | 最多 12,000 字符 |

字符限制不等同于供应商 token 限制。标题、摘要等也参与检索文本组合，正文不足 100,000 不保证组合后一定未超限。

### 17.2 当前没有的能力

- 知乎在线登录、自动同步收藏、抓取正文或下载图片。
- 批量 AI 生成、后台 AI 队列、自动采纳草稿。
- 独立 Opinion 管理、多来源自动合并、拼音排序。
- 多用户、账号权限、云 IAM 鉴权、互联网公开部署方案。
- 多轮聊天、问答历史、混合检索、重排序。
- 网页编辑 Embedding／Qdrant 参数或 RAG 开关。
- 自动更新、安装器、数字签名和跨电脑兼容保证。
- 自动把另一个安装目录的资料迁入当前库。

### 17.3 版本和验收边界

0.6.6 工程验收记录为 **925 项测试通过、3 项 Windows 符号链接权限跳过、1 条已有上游警告**；30 个网页模块检查、受控浏览器以及真实 EXE 的设置／分组／排序／完整桌面流程通过。以上使用隔离数据和模拟模型，不能当成所有供应商或真实 RAG 质量实测。

第四阶段真实 DeepSeek 质量、第五阶段真实 Embedding／问答质量仍单独验收；生产原生“另存为”交互及第二台干净电脑也保留单独验证边界。工程验收和日常功能开关是不同概念，不需要每次使用都重新执行工程验收脚本。

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

说明书核对日期：2026-10-17。本次为文档更新，不修改应用配置、不启动真实模型、不部署服务、不改变个人资料。
