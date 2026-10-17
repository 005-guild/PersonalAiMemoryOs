# RAG 配置与使用指南

适用于 Personal AI Memory OS `0.8.0`，数据库版本 `0006`。本文按当前代码、配置样例和 Compose 文件核对；配置字段的完整范围见[配置参考](config-reference-cn.md)，安装与日常管理见[中文使用说明](../readme-cn.md)。

桌面推荐操作：进入左上角设置的 RAG 分区，填写真实 Embedding 地址、模型、维度、鉴权和密钥引用，选择默认项及 Qdrant 地址。先保存为关闭状态，再分别检查 Qdrant 和向量接口；确认服务可用后才开启并重启。仅保存不发模型请求，Embedding 检测需单独确认且只调用一次，不生成笔记或索引；开启后自动索引全部合格 Knowledge。没有选定向量服务时保持关闭。

引用问答可从独立 Prompt 中心选择 `rag_qa` 用途模板，定制回答重点和风格；固定的出处校验仍有效。Prompt 保存立即供新问题选择，不需重启，也不会改变在途问题使用的模板快照。AI 分析使用另一类 `knowledge` 模板，生成结果在独立草稿箱审阅和采纳。

0.7.0 的合并分析采纳后形成一篇多来源 Knowledge，仍只索引该笔记。引用返回全部来源及当前路径；仅调整来源关联或顺序不改变笔记检索文本时，更新引用元数据而不重新调用 Embedding。AI 批次与引用问答共用一个文本生成额度；批次等待或执行时，问答可能提示繁忙。重启会暂停批次，索引的显式重试规则保持独立。

## 1. 先了解需要准备什么

RAG 把知识笔记转换成向量，找出与问题有关的片段，再让生成模型根据这些片段回答。

```text
知识笔记 Knowledge → Embedding 服务 → Qdrant
                                     ↑
查询/问题 → Embedding 服务 → 找出相关片段 → 生成模型 → 带引用的回答
```

需要准备三个独立部分：

| 部分 | 用途 | 哪些操作需要 |
| --- | --- | --- |
| Embedding 服务 | 将笔记片段和查询转成向量 | 建立/更新索引、语义检索、问答中的检索 |
| Qdrant | 存储向量，查找相近片段 | 索引、检索和问答 |
| 文本生成 AI | 根据检索片段生成带引用的回答 | 引用问答；单纯语义检索不需要 |

生成模型与向量模型可以来自不同服务。已经配好 DeepSeek 或其他聊天模型，不代表已经拥有 Embedding 接口。本程序不会自动下载或启动本地向量模型，也不会自动为你创建供应商账号、密钥或额度。

**只有已保存的“知识笔记”进入索引。** 资料库中的 Source 原文、导入的知乎资料和未采纳 AI 草稿不会直接被索引。先手动建立笔记，或生成草稿并采纳，再使用 RAG。

## 2. 找对当前程序的配置目录

三种运行方式的配置和数据范围如下。桌面版与项目根目录各自独立，不要因为文件同名而编辑错位置。

| 项目 | 便携 EXE | 本机 Python | 项目 Docker Compose |
| --- | --- | --- | --- |
| 运行根目录 | `PersonalAiMemoryOs.exe` 所在目录 | 项目根目录 | 容器中 `/app`，个人文件在宿主机项目中维护 |
| `.env` | EXE 同级 `.env` | 项目 `.env` | 项目 `.env` 供 Compose 读取；仅明确列入 `environment` 的值传给容器 |
| 向量配置 | `config/embedding-providers.yml` | `config/embedding-providers.yml` | 宿主机同名文件，只读挂载至 `/app/config/embedding-providers.yml` |
| 生成配置 | `config/ai-providers.yml` | `config/ai-providers.yml` | 宿主机同名文件，只读挂载至 `/app/config/ai-providers.yml` |
| 默认 SQLite/向量缓存 | `data/memory.db` | `data/memory.db` | 宿主机 `data/memory.db`，挂载至 `/app/data/memory.db` |
| 默认 Markdown | `knowledge/` | `knowledge/` | 宿主机 `knowledge/`，挂载至 `/app/knowledge` |
| Qdrant 地址 | 本机服务通常为 `http://127.0.0.1:6333` | 本机服务通常为 `http://127.0.0.1:6333` | 现有 Compose 固定使用 `http://qdrant:6333` |
| 管理网页 | 桌面窗口，后端使用随机本机端口 | 本文启动命令使用 `http://127.0.0.1:18000/` | `http://127.0.0.1:18000/` |

可在左上角“设置”查看当前运行、数据库、知识和配置路径。桌面版首次启动只补齐缺失模板，不覆盖已有配置；不要编辑 `_internal` 中的资源模板。

**先退出当前应用，再手动修改以下文件。** 修改后重新启动；网页刷新不会重新加载 YAML 或 `.env`。操作系统环境变量优先于 `.env`。Docker 网页设置为只读，应在宿主机维护配置，再重新创建 API 容器。

## 3. 配置 Embedding 服务

### 3.1 确认服务接口和输出维度

当前只实现 `openai_embeddings` 协议：程序向 `base_url + /embeddings` 发 JSON，请求包含 `model`、字符串数组 `input`、`encoding_format: float`。响应需要提供每项的 `index` 和浮点数组 `embedding`。这与 [OpenAI Embeddings 官方接口](https://developers.openai.com/api/reference/resources/embeddings/methods/create)的相应结构一致，但不能据此保证任意“兼容服务”都可用。

向量服务必须真实可访问，并支持你填写的模型、鉴权和请求格式。先从服务文档确认：

1. API 前缀，例如 `https://你的服务/v1`；不要在前缀后重复加 `/embeddings`。
2. 该账号可用的**向量模型 ID**，不能用聊天模型 ID 代替。
3. 实际输出维度；`dimension` 是本程序校验值，不会主动改变模型输出。
4. 是否需要密钥、使用何种鉴权，以及模型的输入 token 上限。

程序默认不发送降维参数。只有服务明确支持时，才填写 `request_dimensions`；它必须与 `dimension` 相等。OpenAI 官方也将 `dimensions` 列为有模型支持条件的参数，不能向所有服务直接照搬。[官方参数说明](https://developers.openai.com/api/reference/resources/embeddings/methods/create)

### 3.2 最小完整向量配置

在当前运行根目录的 `config/embedding-providers.yml` 中设置：

> 以下是结构示例，**不是可直接连通的服务配置**。必须替换 `.invalid` 地址、模型名、密钥，并将 `1024` 改为实际输出维度。不要覆盖自己已经配置好的其他 profiles。

```yaml
schema_version: 1
default_profile: embedding
profiles:
  embedding:
    label: 我的向量服务
    enabled: true
    protocol: openai_embeddings
    base_url: https://embedding.example.invalid/v1
    model: REPLACE_WITH_EMBEDDING_MODEL
    dimension: 1024  # 仅为示例数字，必须核对实际维度
    api_key_ref: embedding
    auth: bearer
    batch_size: 8
    timeout_seconds: 60
```

在当前运行根目录的 `.env` 中**修改对应项**，保留其他配置：

```dotenv
# 准备阶段先关闭，完成地址/模型/维度/密钥和 Qdrant 检查后再开启。
MEMORY_OS_RAG_ENABLED=false
MEMORY_OS_EMBEDDING_CONFIG_FILE=config/embedding-providers.yml
MEMORY_OS_EMBEDDING_DEFAULT_PROFILE=embedding
MEMORY_OS_AI_KEYS__EMBEDDING=REPLACE_WITH_REAL_EMBEDDING_KEY
MEMORY_OS_RAG_QDRANT_URL=http://127.0.0.1:6333
```

`api_key_ref: embedding` 对应 `MEMORY_OS_AI_KEYS__EMBEDDING`。虽然变量名含 `AI_KEYS`，向量密钥也使用这个统一命名空间。密钥放 `.env` 或环境变量，不写入 YAML，不写入聊天消息。

如果使用你已启动的免密本地兼容服务，将 `base_url` 换为其真实地址，设置 `auth: none`，并删除 `api_key_ref`；无需设置向量密钥。例如本机程序连接宿主机模型服务时可能使用 `http://127.0.0.1:8080/v1`，具体端口和模型取决于该服务。

Docker API 容器里的 `127.0.0.1` 指容器自身。若向量服务运行在 Windows 宿主机，Docker Desktop 下通常应把 YAML 的 `base_url` 改为 `http://host.docker.internal:实际端口/v1`，并确认该服务允许 Docker 访问；同一 Compose 网络中的其他模型容器则使用其服务名。该名称的含义见 [Docker Desktop 官方网络说明](https://docs.docker.com/desktop/features/networking/networking-how-tos/)。

现有 Compose 已显式传入 `MEMORY_OS_AI_KEYS__EMBEDDING`。若自行改成其他密钥引用，还要在 Compose 中显式传入对应变量；仅在宿主机 `.env` 新增任意变量不会自动传给 API 容器。

## 4. 准备 Qdrant

当前客户端检查 Qdrant 版本为 **`1.19.x`**，项目固定镜像为 [`qdrant/qdrant:v1.19.2`](https://github.com/qdrant/qdrant/releases/tag/v1.19.2)。不要直接把项目镜像改成 `latest` 后期待接口一定兼容。

### 4.1 已有项目 Compose：只启动 Qdrant

在项目根目录执行以下命令。它只启动 Qdrant，不启动或重新部署 API：

```powershell
docker compose --profile rag up -d qdrant
Invoke-RestMethod -Uri http://127.0.0.1:6333/
```

本机 Python 与桌面 EXE 可以通过 `http://127.0.0.1:6333` 访问这个服务；API 容器通过 `http://qdrant:6333` 访问。Qdrant 的版本信息可由上述 GET 查看；这不产生模型调用。

现有 Compose 使用 `qdrant-storage` 命名卷。实际卷名通常带 Compose 项目前缀。Windows 下继续使用 Docker 命名卷，不要改成把 `D:\...` 直接挂载为 Qdrant 存储目录；[Qdrant 官方排错文档](https://qdrant.tech/documentation/common-errors/)说明了 Windows 共享文件系统与命名卷的区别。

### 4.2 只有便携 EXE，没有项目 Compose

发行的便携目录不包含 `docker-compose.yml`，不能在 EXE 目录直接执行上一节的 Compose 命令；有源码时应切换到项目根目录，否则使用下面的独立容器方式或已有远端服务。

若已安装并运行 Docker，可在 PowerShell 中单独准备 Qdrant：

```powershell
docker volume create personal-memory-qdrant
docker run -d --name personal-memory-qdrant --publish 127.0.0.1:6333:6333 --volume personal-memory-qdrant:/qdrant/storage qdrant/qdrant:v1.19.2
Invoke-RestMethod -Uri http://127.0.0.1:6333/
```

这与项目 Compose 是两种启动方法，选择一种即可；如果 6333 已有 Qdrant，不要再启动第二份争用端口。创建过的独立容器以后用 `docker start personal-memory-qdrant` 启动，用 `docker stop personal-memory-qdrant` 停止。

便携 EXE 本身不包含 Qdrant。没有 Docker 时，可以连接另一台设备上已运行的兼容 Qdrant：在 EXE 同级 `.env` 中将 `MEMORY_OS_RAG_QDRANT_URL` 改为实际 HTTP(S) 地址，再重启 EXE。本机基础资料和笔记管理不要求 Docker。

**远端接入有明确边界：** 当前程序没有 Qdrant API Key 或自定义认证头配置，URL 也不接受用户名、密码或查询参数。需要 API Key 的托管 Qdrant 不能仅填写 URL 就接通。应使用应用可直达、版本匹配、无需该鉴权头且受可信网络访问限制的端点；不要将上述免密本机测试服务直接公开到互联网。

### 4.3 API 也使用 Docker

项目 Compose 将 API 的 Qdrant 地址固定为 `http://qdrant:6333`；宿主机 `.env` 的同名值不会覆盖这项固定设置。若连接外部 Qdrant，需要调整 Compose 的 API `environment` 或使用显式覆盖文件。

配置准备完成、RAG 设为 `true` 后，可在项目根目录执行：

```powershell
docker compose --profile rag up -d qdrant
docker compose --profile rag up -d --force-recreate api
```

以上假定已按主说明完成镜像和数据库初始化。首次部署请先完成[中文使用说明](../readme-cn.md)的 Docker 安装、迁移和启动步骤。更改环境变量应重新创建 API；仅刷新网页或执行容器内页面操作不会加载新的配置。

## 5. 开启、检查并建立第一份索引

### 5.1 先决定只检索还是也问答

| 目标 | `MEMORY_OS_RAG_ENABLED` | `MEMORY_OS_AI_ENABLED` | 额外要求 |
| --- | --- | --- | --- |
| 普通资料/笔记管理 | 可为 `false` | 可为 `false` | 不需要模型或 Qdrant |
| 语义检索 | `true` | 可以为 `false` | 向量配置就绪、Qdrant 可用、索引已发布 |
| 引用问答 | `true` | `true` | 上述条件，加一套就绪的文本生成配置 |

如果只用检索，保持 `MEMORY_OS_AI_ENABLED=false` 即可。

需要问答时，可在左上角“设置”维护生成配置，或编辑 `config/ai-providers.yml`。已有可用生成配置可直接沿用。以下完整结构仅供没有配置时参考：

```yaml
# 地址和模型仍是不可直接使用的占位符；须换成实际兼容服务。
schema_version: 1
default_profile: answer
profiles:
  answer:
    label: 我的问答生成模型
    enabled: true
    protocol: openai_chat
    base_url: https://generation.example.invalid/v1
    model: REPLACE_WITH_GENERATION_MODEL
    api_key_ref: openai  # 引用名，不强制供应商；此名称已有 Compose 密钥映射
    auth: bearer
    response_format: prompt
    max_output_tokens: 4096
    timeout_seconds: 90
```

对应 `.env` 中设置 `MEMORY_OS_AI_KEYS__OPENAI=你的实际生成密钥`、`MEMORY_OS_AI_ENABLED=true`；若已有 `MEMORY_OS_AI_DEFAULT_PROFILE`，确认它也指向有效配置，否则它会覆盖 YAML 的默认项。完整生成协议选择见[配置参考](config-reference-cn.md)。

### 5.2 开启前注意调用范围

将当前运行根目录 `.env` 的 `MEMORY_OS_RAG_ENABLED` 改为 `true` 后重启。**后台启动后就会检查全部已提交笔记，并为需要的片段调用 Embedding；不需要再点“更新索引”才开始。** 初次开启前应确认模型、维度、数据范围和调用预算。

- 桌面版：完全退出后双击同一目录的 EXE。
- 本机 Python：停止原进程，再从项目根目录按原启动方式启动。例如 `uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 18000`。
- Docker：按上一节重新创建 API，并确保 Qdrant 已启动。

不要让本机与容器服务同时管理同一份 SQLite/知识目录。桌面版默认另用便携目录中的独立数据。

### 5.3 在网页中检查

1. 打开“同步与系统”，查看“知识索引”和“模型配置”中的 Embedding 状态。
2. 确认 RAG 已开启、默认向量配置正确、所需密钥已配置。
3. 查看索引代次、待处理、失败和错误列表。默认每轮对账完成后等待 5 秒，再进行下一轮。
4. 有需要时点“更新索引”；确认框会说明可能调用向量服务。提交成功只表示排队，不表示索引已完成。
5. 等待本轮结束，再打开“搜索问答”中的“语义检索”。

“配置就绪”只说明本机配置可加载且所需密钥存在；它不会探测密钥有效性、网络、模型权限、余额或生成质量。`/health` 仍只反映原有服务和数据库健康，不能证明 RAG 可用。

## 6. 搜索、问答和真实 API 示例

网页入口为“搜索问答”：在“语义检索”查看片段和相似度；在“引用问答”选择生成模型并提问。`top_k` 是片段数，不是笔记篇数；同一笔记可能命中多段。

API 的统一前缀是 `/api/v1/rag`。以下 JSON 可直接填入 Swagger 的请求体；本机和项目 Docker 的 Swagger 通常在 `http://127.0.0.1:18000/docs`。桌面后端端口由系统分配，不能将另一个 18000 服务误认为 EXE 的数据。

| 操作 | 方法和路径 | 请求体 |
| --- | --- | --- |
| 查看向量配置状态 | `GET /api/v1/rag/embedding-profiles` | 无 |
| 查看索引状态 | `GET /api/v1/rag/index/status` | 无 |
| 普通增量更新 | `POST /api/v1/rag/index/run` | `{"retry_failed":false}` |
| 显式重试失败项 | `POST /api/v1/rag/index/run` | `{"retry_failed":true}` |
| 创建新代次并重建 | `POST /api/v1/rag/index/rebuild` | 无请求体 |
| 语义检索 | `POST /api/v1/rag/search` | `{"query":"索引有什么成本？","top_k":5}` |
| 引用问答 | `POST /api/v1/rag/ask` | `{"question":"索引有什么成本？","top_k":5}` |

问答可额外传 `"profile_id":"answer"` 选择**生成配置**；省略时用默认生成配置。它不会选择向量模型。索引/搜索使用当前默认 Embedding 配置，以上接口没有 `embedding_profile_id` 参数。

问答还可提交 `prompt_template_id` 与 `prompt_template_version` 选择 Prompt 中心的 `rag_qa` 模板；不传时使用该用途默认项。笔记解析模板不能用于问答。请求固定使用开始时的模板版本，响应中的 `prompt_template` 提供 ID、版本、名称、用途和 `content_hash`，`prompt_hash` 对应模板与固定引用合同组成的实际系统提示词。编辑模板不会改变已在执行的问答。

索引操作成功返回 HTTP 202，例如普通更新返回：

```json
{"status":"queued","retry_failed":false,"rebuild":false}
```

随后查询 `/index/status` 观察最终结果。不要因为 202 就立即断定成功，也不要因等待较久反复提交。

检索返回 `items` 和 `index_incomplete`。每个片段包含笔记 UUID、版本、标题、当前 Markdown 路径、关联来源、文本、相似度、片段 ID、内容哈希和代次 ID。相似度没有经过真实模型校准的固定“合格分数线”，不要把它当作正确率。

问答返回 `answer`、`paragraphs`、`citations`、`insufficient_evidence`、`index_incomplete`、模型配置与可用 `usage`。每段必须引用本次上下文中的片段，引用摘录必须真实存在于对应片段。网页中的引用可以跳回原笔记。

当没有有效片段时，程序返回“知识库依据不足”，不会再调用生成模型；但问答入口仍先要求生成 AI 已启用、配置可解析。检索得到片段后，模型也可以判断依据不足。引用校验能保证摘录可追溯，不能替代人工判断回答是否忠实。当前为单轮问答，不保存问答历史。

## 7. 日常更新、重试、重建与恢复

### 日常笔记变动

RAG 启用期间，后台以 SQLite 中已提交的 Knowledge 为依据，覆盖网页/API 编辑、Markdown 回写、草稿采纳、软删除、恢复和冲突解决。

- 仅移动或重命名 Markdown 文件，更新引用路径，不因路径变化重新计算向量。
- 等待 Markdown 导出不会阻止有效数据库内容进入索引。
- 已删除、存在开放同步冲突或同步错误的笔记不会参与检索；先在“同步与系统”处理问题。
- 更新后的旧向量即使尚未清理，也会经过数据库版本和哈希核验，不能继续作为当前回答的依据。

“更新索引”用于主动进行一次增量对账。无变化且已有有效发布的笔记不会重复向量化。

### 显式重试失败项

失败、超时、调用结果不明或进程中断后的 Embedding 任务，不会因每 5 秒对账而自动重复调用。先检查错误、服务权限和余额，再点“重试失败项”，或提交 `{"retry_failed":true}`。

重试可能再次计费：客户端超时并不能证明服务端没有完成收费调用。重试仅补齐缺失向量；已成功保存的兼容缓存可以继续使用。笔记内容后来发生真实变化时，会按新内容生成新任务，不能把“失败不自动重试”理解为永远不会再产生新调用。

### 换向量模型或分块规则

1. 等待当前操作结束，退出应用；备份 SQLite、完整知识目录和配置。
2. 修改向量 profile 的 API 地址、模型、实际维度或相关设置，必要时同步更换密钥。
3. 改变同名模型背后的版本时，填写/更新 `model_revision`，使项目能识别语义版本变化。此字段用于配置指纹，不会作为参数传给模型服务；实际版本仍需你在服务端保证。
4. 重启后，若出现 `rag_rebuild_required`，执行一次“重建索引”。它会创建独立新代次和 collection，重建期间检索可能不可用。
5. 查看状态和错误；存在之前未确认结果的失败项时，仍须单独显式重试。

地址、模型、`model_revision`、维度、显式降维、扩展参数及分块/长度规则参与兼容性判断；不要仅把 `dimension` 改成新数字后继续使用旧向量。更换密钥、标签、批大小或超时本身不等于向量语义变化。完整指纹字段见[配置参考](config-reference-cn.md)。

### Qdrant 暂时故障或向量存储丢失

SQLite 保存成功的向量缓存、笔记版本和发布状态，Qdrant 保存可检索的向量点。

- 网络/服务暂时中断：先恢复原 Qdrant；后台可重新上传已缓存向量，不需要重复调用模型。
- 原 collection 整体缺失：服务会按数据库记录建立所属 collection，并尝试从 SQLite 中仍完整的缓存恢复。缓存缺失或笔记已变更的部分可能需要新 Embedding。
- collection 还在、但被手工删了部分向量点：普通对账不承诺发现所有这种手动破坏；确认备份和费用后重建，可重新发布兼容缓存或生成缺失向量。
- SQLite 也丢失：只有 Qdrant 卷不能恢复笔记、版本和发布清单，必须先恢复应用数据库及完整知识目录。

同一兼容配置下重建可复用仍完整、文本一致的缓存；不保证所有历史缓存永久保留。成功替换后会清理旧缓存，避免把“有缓存”误认为永远不再收费。

### Collection 所有权和备份

程序自动生成 `memory_os_...` collection 名称，使用 Cosine 距离、对应维度和应用/代次/owner 元数据。创建、写入、清理旧点和删除旧 collection 前会检查所有权；不要手工预建同名 collection，也不要修改其元数据来绕过错误。

出现 `qdrant_collection_ownership_mismatch` 时，先确认是否接错 Qdrant 或混用了不同数据库的向量存储，不要直接清空整个 Qdrant。重建会清理本应用拥有的退休代次，不应借此操作其他应用的 collection。

备份至少保留 SQLite、完整知识目录和配置。若希望保留 Qdrant 当前索引，还应另行备份命名卷或按 Qdrant 的备份流程处理；复制项目文件夹不会自动包含 Docker 命名卷。不要用 `docker compose down -v` 当作普通重启命令，它会请求删除 Compose 管理的卷。

## 8. 看懂索引状态

| 字段 | 含义与下一步 |
| --- | --- |
| `enabled` | 启动时加载的 RAG 开关；手动修改 `.env` 后尚未重启不会改变此值 |
| `worker_running` | 自动对账后台是否运行，不表示当前正在请求模型 |
| `running` | 当前是否有一轮索引处理正在进行 |
| `last_scan_at` | 上次对账结束时间，不是“所有笔记已成功”的证明 |
| `generation` | 当前代次；初次运行前可能为空；`building` 构建中，`ready` 可进入检索检查 |
| `counts.published` | 已发布且与当前笔记版本/内容一致的笔记数，不是分块数 |
| `counts.pending` | 尚未有效发布的可索引笔记数；需结合错误列表判断等待原因 |
| `counts.failed` | 当前内容对应的失败/中断笔记数，通常需要检查后显式重试 |
| `counts.excluded` / `excluded` | 删除、同步冲突或同步错误导致的排除记录；正常软删除也会计入 |
| `errors` | 逐笔记的错误码；长文超限等也在这里查看 |
| `last_error` | 最近整轮错误，可能是配置、重建要求或 Qdrant 故障 |
| `index_incomplete` | 索引未覆盖当前应可用内容，或有活跃笔记被冲突/同步错误排除 |

`generation.status=ready` 仍可能有失败笔记，应同时查看 `index_incomplete`、计数与错误。部分完成时可以返回已发布且有效的片段，并标记索引不完整；故障或完全未准备好时会报不可用，不会伪装成“空知识库”。

## 9. 调用与数据量边界

以下为当前默认值；可配置项和可接受范围见[配置参考](config-reference-cn.md)。

| 项目 | 默认/固定边界 |
| --- | --- |
| 索引文本 | 组合标题、摘要、分类、标签、概念和正文；不包含 Source 原文 |
| 分块 | 1,200 字符一块，重叠 200 字符；不是按自然段或 token 切分 |
| 单篇上限 | 组合后的检索文本 100,000 字符、最多 200 块；超限报错，不截掉尾部 |
| Embedding 批次 | 默认/最多 8 块，可配置为 1–8；默认每次调用总时限 60 秒 |
| Embedding 响应 | 最大 16 MiB；校验数量、索引、维度、有限数值及非全零向量 |
| 查询/问题 | 去除首尾空白后 1–2,000 字符 |
| `top_k` | 默认 5，允许 1–10 个片段 |
| 问答上下文 | 最多 12,000 字符的片段文本；另有提示词、标题和问题开销 |
| 生成模型 | 沿用所选生成 profile，默认输出上限 4,096 tokens、总时限 90 秒；响应最大 1 MiB |
| 并发 | 问答与草稿共享单个生成额度；查询向量化一次一个，后台索引按批串行，不代表与查询合计只会有一个向量请求 |

字符数不等于服务端 token 数。长代码、特定语言或模型上下文限制仍可能导致供应商拒绝请求；本项目不会自动缩短资料、降级协议、切换服务或修复输出后重试。

可能触发模型请求的操作：

- **RAG 启动与自动对账**：首次索引、新建/修改笔记、恢复后缺少兼容缓存时，可能调用 Embedding。
- **更新/显式重试/重建**：根据缓存和任务状态，可能调用 Embedding；重建不代表必然全部重新收费，也不代表必然零费用。
- **语义检索**：已有可用片段时，通常把本次查询向量化一次；相同查询不保证复用查询缓存。
- **引用问答**：先检索；存在上下文时再主动调用一次选定的生成模型，模型最终也可能回答依据不足。
- **设置中的 Embedding 测试**：确认后发送一次固定短文本，可能计费；不创建索引、不修改笔记或向量缓存。Qdrant 连接检查只读取根接口 `GET /`，不创建或修改 collection。
- **只查看配置、索引状态、页面状态或健康检查**：不主动调用模型。后台 RAG 若已启用，仍可能独立进行索引。

使用云端向量服务时，索引文本和查询会发往所配置端点；问答会向生成服务发送问题与选中的知识片段。是否收费及数据保留规则由你选择的服务决定，不应把“程序本机运行”理解为所有数据处理都离线。

## 10. 常见错误与排查顺序

错误通常位于响应 `detail.code`；索引后台错误也会显示在状态页。

| 错误/现象 | 处理方式 |
| --- | --- |
| `rag_disabled` | 修改正确运行根目录的开关并重启；Docker 重新创建 API |
| `embedding_configuration_missing` / `embedding_configuration_invalid` | 检查当前运行根目录 YAML 路径、UTF-8、字段类型、重复键、默认 profile 和维度 |
| `embedding_default_profile_missing` / `embedding_profile_unknown` / `embedding_profile_disabled` | 检查 YAML 默认项、`.env` 覆盖项及 profile 的 `enabled` |
| `embedding_api_key_missing` | 检查 `api_key_ref` 与环境变量名；Docker 还要检查是否显式传入容器 |
| `embedding_upstream_error` | 检查实际前缀、模型权限、鉴权、余额和服务状态；不要把整个 `/embeddings` 再填进前缀 |
| `embedding_response_invalid` | 检查兼容响应格式、index、维度、向量数量/数值；不要只改本地维度数字来掩盖错误 |
| `embedding_timeout` / `embedding_call_interrupted` / `embedding_retry_required` | 结果可能不明；确认后再使用显式失败重试，避免反复点击 |
| `rag_document_too_large` / `rag_too_many_chunks` | 缩短或拆分笔记，或按实际模型限制调整配置后重建；不会静默截断 |
| `rag_index_missing` / `rag_index_building` / `rag_index_not_ready` | 查看索引状态，等待初建；若失败则先解决配置和后端错误 |
| `rag_rebuild_required` | 配置与当前代次不兼容，按换模型步骤显式重建 |
| `qdrant_unavailable` / `qdrant_timeout` | 检查 Qdrant 进程、端口和网络；容器不要用自身 `127.0.0.1` 连接宿主机服务 |
| `qdrant_version_unsupported` | 使用当前支持的 `1.19.x`；项目镜像为 `1.19.2` |
| `qdrant_collection_ownership_mismatch` / `qdrant_collection_schema_mismatch` | 确认数据库、Qdrant 与代次是否匹配；不手动改所有权或清空其他数据 |
| `rag_index_unavailable` | 查看索引状态的 `last_error`；原有 CRUD 和 `/health` 正常不代表索引正常 |
| `ai_disabled` / `ai_api_key_missing` 等 | 问答额外依赖文本生成配置；只检索不要求开启 AI |
| HTTP 429，`generation_busy` / `embedding_query_busy` / `rag_index_busy` | 等当前操作结束再手动提交；不自动重试 |
| HTTP 409，`context_changed` | 检索/生成期间引用内容、可用状态或代次发生变化；先核对笔记，再决定是否重新提问 |
| HTTP 502，`invalid_qa_output` | 生成结果引用或结构不符合要求；没有自动修复/再次付费调用，可换问题或检查模型兼容性后主动重试 |
| 只有“知识库依据不足” | 确认已有 Knowledge、已采纳所需草稿、索引完整且无同步冲突；它不等于程序会读取资料库原文补全答案 |

建议依次检查：**当前运行目录 → RAG/AI 开关 → profile/密钥就绪 → Qdrant → 索引错误 → Knowledge 是否有效 → 查询和回答质量**。真实服务的摘要忠实度、检索相关性和引用回答质量仍需用自己的样例人工验证；工程模拟验收不等于所有供应商均已实测通过。
