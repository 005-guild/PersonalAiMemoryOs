# 配置完整参考（v0.8.0）

本文说明当前应用实际读取哪些配置、默认值是什么、修改后怎样生效。适用于源码本机服务、Windows 便携 EXE 和项目自带 Docker Compose；数据库结构为 `0006`。模型名称和地址示例来自项目模板，不代表已经逐个完成真实服务验收。

日常操作见 [中文使用说明](../readme-cn.md)，向量索引、搜索和引用问答的完整步骤见 [RAG 使用指南](rag-guide-cn.md)。本文的配置依据是 [Settings](../app/config.py)、[文本配置与适配器](../app/agents/configuration.py)、[Embedding 配置](../app/vector/configuration.py) 和 [Compose](../docker-compose.yml)。

当前源码、固定桌面与独立旧 Docker API 的版本／存储范围见 [实例矩阵](project-audit-cn.md#current)。后续恢复、冷启动和空间保留任务见 [维护清单](project-audit-cn.md#priorities)；它们是待实施／待验收事项，不是隐藏配置项。

## 1. 配置放在哪里，按什么顺序读取

| 运行方式 | 运行根目录 | 个人配置与数据 | 修改后生效方式 |
| --- | --- | --- | --- |
| 源码本机服务 | 项目根目录 | 根目录 `.env`、`config/`、`data/`、`knowledge/` | 停止并重新启动服务 |
| Windows 便携 EXE | `PersonalAiMemoryOs.exe` 所在目录 | 同目录中的 `.env`、`config/`、数据、日志和缓存 | 完全退出应用后重新打开；重复双击已有实例不等于重启 |
| Docker Compose | 容器内 `/app` | 宿主机 `./data`、`./knowledge` 和只读挂载的 `./config`；密钥由 Compose 环境传入 | 修改宿主机配置；环境变量变化需重新创建 API 容器 |

常用文件：

```text
运行根目录/
├── .env                              # 开关、运行参数、密钥
├── config/
│   ├── ai-providers.yml               # 文本生成模型配置
│   └── embedding-providers.yml        # 向量模型配置
├── data/memory.db                    # SQLite 与索引缓存
└── knowledge/                       # Markdown 笔记及隐藏身份标记
```

EXE 首次运行只补齐缺失的公开模板，不覆盖已有配置；新空库会初始化，已有旧库升级需要确认并先备份。源码和 Docker 服务仍要求显式执行迁移。不要删除已有知识目录的 `.memory-os-vault` 标记，数据库与完整知识目录应成对保留。

通常的读取优先级为：**程序显式传入的 Settings 值 → 进程环境变量 → 当前运行方式选择的 `.env` → 代码默认值**。例如系统环境中已有 `MEMORY_OS_AI_ENABLED=false`，在 `.env` 或网页中设置 `true` 也不能覆盖这个进程环境值。网页会显示环境托管提示，并阻止不被允许的修改。

文本配置的默认项按 `MEMORY_OS_AI_DEFAULT_PROFILE` 的非空值优先，否则使用文本 YAML 的 `default_profile`；Embedding 同理。请求支持指定 `profile_id` 的地方，显式请求值优先于默认项。默认 ID 必须存在，不会自动选择第一个配置或切换服务。

`.env` 使用 UTF-8；布尔值建议写 `true` / `false`。YAML 使用真正的布尔值和数字，例如 `enabled: true`、`timeout_seconds: 90`，不要全部加引号。未知 YAML 字段、重复键和非法类型会被拒绝；未知 `.env` 字段会被忽略，因此拼错变量名可能不会产生明确报错。

运行 Settings 本身校验失败通常会阻止服务启动。文本或 Embedding YAML 缺失、非法时，对应模型注册器会报告配置错误，普通资料管理、笔记管理与数据库健康检查仍可使用；设置页面也可能无法读取非法文件，需先在本机修正。

## 2. 全部 Settings 环境变量

以下“默认值”指代码默认值。公开 `.env.example` 只列常用项；未列出的 Settings 字段仍可通过正确的环境变量配置。

Compose 列的“可透传”表示当前文件已有 `${变量:-默认值}`；“固定”表示当前 Compose 明确写死该值；“未传入”表示仅修改宿主机 `.env` 不会把该项送入容器。范围端点均包含在内。

### 2.1 目录、数据库与日志

| 环境变量 | 代码默认值 | 校验与作用 | 当前 Compose |
| --- | --- | --- | --- |
| `MEMORY_OS_RUNTIME_ROOT` | 源码项目根目录 | 内部运行根目录字段；EXE 由启动器显式指定为 EXE 目录。普通用户不要用它切换数据位置 | 未传入；镜像代码根为 `/app` |
| `MEMORY_OS_DATABASE_URL` | `sqlite:///data/memory.db` | 仅支持文件型 `sqlite` / `sqlite+pysqlite`；相对数据库文件按项目根解析。拒绝内存库、SQLite URI、查询参数和网络数据库连接信息 | 固定 `sqlite:////app/data/memory.db` |
| `MEMORY_OS_KNOWLEDGE_DIR` | `knowledge` | 非空，必须是运行根目录内的子目录，不能直接使用运行根目录 | 固定 `/app/knowledge` |
| `MEMORY_OS_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` | 固定 `INFO` |
| `MEMORY_OS_CONFIGURATION_READ_ONLY` | `false` | 是否禁止网页保存 AI 与 RAG／Embedding 配置；不会禁止普通资料与笔记写入 | 固定 `true` |

源码模式的数据库路径校验与 EXE 的便携隔离规则不同：EXE 还会拒绝数据库、知识或配置路径超出便携目录，并拒绝符号链接和目录联接。移动便携版时，优先保留相对路径；目录内绝对路径在整体移动后也需要核对。

文本和 Embedding 配置文件必须位于运行根目录内。网页设置不能修改数据路径；网页配置写入的 YAML 目标还不能是 `.env`、数据库、知识目录、`data/` 或配置恢复目录。设置页面展示的数据库文件、数据目录和知识目录是只读信息。

AI 和 Embedding YAML 也不能使用同一个路径。手工修改配置文件路径后，先重启应用再在网页保存；否则可能返回 `configuration_path_changed`，以免写入旧进程正在使用的错误位置。

### 2.2 Markdown 同步

| 环境变量 | 默认值 | 范围与作用 | 当前 Compose |
| --- | --- | --- | --- |
| `MEMORY_OS_SYNC_ENABLED` | `true` | 启用后台 Markdown 双向同步 | 固定 `true` |
| `MEMORY_OS_SYNC_INTERVAL` | `2.0` | `0.05–3600` 秒；后台完整扫描的间隔。文件仍需满足稳定性检查 | 固定 `2` |
| `MEMORY_OS_DELETION_GRACE` | `10.0` | `0–86400` 秒；文件缺失软删除的最短宽限期，还需满足完整扫描次数等条件 | 固定 `10` |

关闭同步不会让知识数据库只读。文件未导出与同步冲突也不是同一状态；索引是否排除笔记另由 RAG 的有效性检查决定。

### 2.3 文本生成 AI

| 环境变量 | 默认值 | 范围与作用 | 当前 Compose |
| --- | --- | --- | --- |
| `MEMORY_OS_AI_ENABLED` | `false` | 文本生成总开关；控制草稿生成和问答中的生成步骤 | 可透传，默认 `false` |
| `MEMORY_OS_AI_CONFIG_FILE` | `config/ai-providers.yml` | 非空、运行根目录内的 YAML 路径；相对路径按运行根目录解析 | 固定 `/app/config/ai-providers.yml` |
| `MEMORY_OS_AI_DEFAULT_PROFILE` | `null` | 可选默认文本配置 ID；空字符串按未覆盖处理 | 可透传，默认空 |
| `MEMORY_OS_AI_KEYS` | `{}` | 密钥字典；通常使用下文的 `MEMORY_OS_AI_KEYS__引用` 分项形式。文本和 Embedding 共用这个密钥表 | 未传入整个字典；明确传入下列 10 个引用 |
| `MEMORY_OS_AI_MAX_INPUT_CHARS` | `20000` | `1–2000000`；生成草稿允许的 Source 正文最大字符数。超限报错，不自动截断 | 可透传，默认 `20000` |

当前 Compose 透传的密钥分项是：`OPENAI`、`DEEPSEEK`、`QWEN`、`SILICONFLOW`、`DOUBAO`、`KIMI`、`GLM`、`ANTHROPIC`、`GEMINI`、`EMBEDDING`，完整变量名为 `MEMORY_OS_AI_KEYS__<引用>`。

`AI_MAX_INPUT_CHARS` 是正文字符上限，不是供应商 token 上限，也不控制问答检索上下文大小。实际发送还包含提示词及资料元信息，接入真实服务时需要核对该服务的输入限制。

### 2.4 Embedding、索引与 Qdrant

| 环境变量 | 默认值 | 范围与作用 | 当前 Compose |
| --- | --- | --- | --- |
| `MEMORY_OS_RAG_ENABLED` | `false` | RAG 总开关；启用自动索引、语义搜索及问答的检索部分 | 可透传，默认 `false` |
| `MEMORY_OS_EMBEDDING_CONFIG_FILE` | `config/embedding-providers.yml` | 非空、运行根目录内的 YAML 路径 | 固定 `/app/config/embedding-providers.yml` |
| `MEMORY_OS_EMBEDDING_DEFAULT_PROFILE` | `null` | 可选默认向量配置 ID；空字符串按未覆盖处理 | 可透传，默认空 |
| `MEMORY_OS_RAG_QDRANT_URL` | `http://127.0.0.1:6333` | HTTP(S) 地址前缀；不允许用户名、密码、查询参数、片段或反斜杠 | 固定 `http://qdrant:6333` |
| `MEMORY_OS_RAG_INTERVAL` | `5.0` | `0.05–3600` 秒；后台索引对账间隔 | 未传入 |
| `MEMORY_OS_RAG_CHUNK_CHARS` | `1200` | `100–8000` 字符；确定性分块长度 | 未传入 |
| `MEMORY_OS_RAG_CHUNK_OVERLAP` | `200` | `0–2000` 字符，且必须小于分块长度 | 未传入 |
| `MEMORY_OS_RAG_MAX_NOTE_CHARS` | `100000` | `1–2200000`；单篇组织后的检索文本上限，包含标题等元数据与正文 | 未传入 |
| `MEMORY_OS_RAG_MAX_CHUNKS` | `200` | `1–2000`；单篇最多块数，超限明确失败 | 未传入 |

这些字符与块数限制都不会静默丢弃尾部。改变分块长度、重叠、上限或分块实现版本会改变索引配置指纹，需要显式重建。

当前客户端校验 Qdrant `1.19.x`；Compose 固定镜像为 `qdrant/qdrant:v1.19.2`。Qdrant 数据使用命名卷，应用的 SQLite 和 Markdown 仍使用项目目录。当前没有 Qdrant API Key 配置项，也没有向其请求添加认证头；不要自行假设某个 `MEMORY_OS_QDRANT_API_KEY` 变量会生效。

监听地址和端口不在这 22 个 Settings 字段中。源码服务由 Uvicorn 启动参数决定端口；Compose 将宿主机 `127.0.0.1:18000` 映射到容器 8000；EXE 自行分配空闲本机端口。设置 `MEMORY_OS_PORT` 不会改变这些行为。

## 3. 文本模型 YAML：完整字段

从 [公开文本模板](../config/ai-providers.example.yml) 复制为个人 `config/ai-providers.yml`，或在工作台左上角“设置”中维护。YAML 顶层结构为：

```yaml
schema_version: 1
default_profile: deepseek
profiles:
  deepseek:
    label: DeepSeek
    enabled: true
    protocol: openai_chat
    base_url: https://api.deepseek.com
    model: deepseek-flash
    api_key_ref: deepseek
    response_format: json_object
    max_output_tokens: 4096
    timeout_seconds: 90
    extra_body:
      thinking:
        type: disabled
```

`schema_version` 必须是整数 `1`；`profiles` 最多 100 个。配置 ID 是 `profiles` 下的键，需匹配 `[a-z][a-z0-9_-]{0,63}`，即小写字母开头、总长最多 64，后续可用数字、短横线和下划线。`default_profile` 可以是 `null`，但未指定默认项时，发起生成必须显式选配置。

| profile 字段 | 默认值／是否必填 | 范围与作用 |
| --- | --- | --- |
| `label` | `null` | 显示名称；非空时 1–200 字符，不能只含空白或控制字符；未填则显示 ID |
| `enabled` | `true` | 允许主动选择该配置；全局 AI 关闭时它仍不能生成。网页新建模板默认停用，需主动勾选 |
| `protocol` | 必填 | `openai_chat` / `openai_responses` / `anthropic_messages` / `gemini_generate_content` |
| `base_url` | 必填 | 1–2048 字符的 HTTP(S) **地址前缀**，含所需版本路径；不填完整生成接口。拒绝 URL 凭据、查询参数、片段、空白和反斜杠，末尾 `/` 会去除 |
| `model` | 必填 | 1–200 字符的模型 ID；非纯空白且无控制字符。按自己的服务、账户和区域填写 |
| `api_key_ref` | `null` | 引用本机密钥表中的名称，匹配 `[a-zA-Z][a-zA-Z0-9_-]{0,63}`；比较时不区分大小写 |
| `auth` | `auto` | `auto` / `bearer` / `x_api_key` / `x_goog_api_key` / `none`，映射见下节 |
| `response_format` | `prompt` | `prompt` 表示通过提示词约束业务 JSON；仅 Chat 可以选 `json_object` 并发送对应请求参数。其余协议必须是 `prompt` |
| `max_output_tokens` | `4096` | 整数 `1–131072`；由适配器映射为各协议的输出限额字段。是否被供应商接受由实际模型决定 |
| `timeout_seconds` | `90.0` | `0.01–600` 秒；整个单次调用时限，而非自动重试次数 |
| `token_limit_field` | `max_tokens` | Chat 可选 `max_tokens` / `max_completion_tokens`；其他协议须保留 `max_tokens`，实际输出字段由适配器自行映射 |
| `anthropic_version` | `2023-06-01` | `YYYY-MM-DD` 形式；仅 Anthropic 适配器发送为 `anthropic-version` 请求头。YAML 中建议加引号以保留字符串类型 |
| `extra_body` | `{}` | 受限 JSON 对象，用于供应商扩展参数；不会添加任意认证头，限制见第 5 节 |

生成与引用问答复用同一套文本配置。配置中没有独立的“草稿模型”和“问答模型”字段；在支持 `profile_id` 的主动请求或页面中选择对应 profile 即可。

## 4. 四种文本协议与鉴权

### 4.1 URL 和字段映射

适配器直接将以下路径追加到 `base_url`，不会自动补 `/v1`、切换协议或跟随重定向。

| `protocol` | 追加路径 | 核心请求映射 | 最终正文来源 |
| --- | --- | --- | --- |
| `openai_chat` | `/chat/completions` | `messages`，`stream: false`；输出限额取 `token_limit_field` | 第一个 choice 的 assistant `content` |
| `openai_responses` | `/responses` | `instructions` + `input`，`max_output_tokens`，`stream: false`，`store: false` | 完成的 assistant message 内 `output_text` |
| `anthropic_messages` | `/messages` | `system` + user `messages`，`max_tokens`，`stream: false` | `content` 中的 `text` 块 |
| `gemini_generate_content` | `/models/{model}:generateContent` | `systemInstruction` + `contents`，`generationConfig.maxOutputTokens` | 第一个 candidate 中非 thought 的文本 parts |

例如 OpenAI 模板的前缀是 `https://api.openai.com/v1`；DeepSeek 模板是 `https://api.deepseek.com`；Claude 模板前缀含 `/v1`；Gemini 模板前缀含 `/v1beta`。照抄某个平台前缀时，还需核对它是否与所选协议相符。Gemini 的 `model` 填模型 ID，不要自行重复加 `/models/` 路径。

### 4.2 鉴权映射

| `auth` | 文本生成行为 | Embedding 行为 |
| --- | --- | --- |
| `auto` | Chat / Responses 使用 Bearer；Anthropic 使用 `x-api-key`；Gemini 使用 `x-goog-api-key` | 使用 Bearer |
| `bearer` | `Authorization: Bearer <密钥>` | 相同 |
| `x_api_key` | `x-api-key: <密钥>` | 相同 |
| `x_goog_api_key` | `x-goog-api-key: <密钥>` | 相同 |
| `none` | 不发送认证密钥，不要求 `api_key_ref` | 相同 |

需要认证的配置必须有有效引用且密钥非空。单纯省略 `api_key_ref` 不代表免密；本地免密兼容服务必须明确填 `auth: none`。本版没有任意自定义请求头、云平台 IAM、OAuth 或自动令牌刷新配置。

### 4.3 项目模板中的平台示例

公开文本 YAML 提供 DeepSeek、OpenAI Chat/Responses、Claude、Gemini，以及 Chat 兼容的千问/百炼、硅基流动、豆包/Ark、Kimi、智谱和本地服务示例。DeepSeek 是模板默认项，其他示例默认停用，多数模型字段仍是 `replace-with-your-model`。

这些是协议配置起点；兼容 API 不一定支持相同的可选参数、模型 ID 或账户权限。应用不自动更换厂商、降级输出格式或重试。`configured` 只表示本地配置具备所需密钥或使用免密方式，不代表已经验证连通性、余额、模型可用性和输出质量。

文本响应上限固定为 1 MiB，草稿与问答共享一个文本生成并发额度；这些不是额外的 profile 字段。当前 Compose 的退出宽限是 150 秒，调大单次模型超时不会自动延长这个容器退出期限，应在部署配置中一起核对。

## 5. 扩展参数与 DeepSeek 思考开关

### 5.1 `extra_body` 的边界

扩展参数递归合并到该协议的请求体。它必须是合法 JSON 对象：最多递归 12 层，序列化后的校验长度不超过 32768，数值必须有限，不接受 `NaN` / `Infinity` 或任意 YAML 对象。

校验会递归检查所有层级的字段名，转小写并去除非字母数字后检查保留名。不能通过改变大小写、加下划线或嵌套来覆盖模型、消息、提示词、认证、流式模式、输出限额、结构化输出、工具调用和会话等受保护内容。文本生成的保留名为：

```text
model messages message input instructions system prompt contents systeminstruction
stream streamoptions maxtokens maxcompletiontokens maxoutputtokens maxinputtokens
responseformat format tools tool toolchoice functions functioncall
apikey authorization authentication auth headers token accesstoken bearertoken credentials
n candidatecount store background previousresponseid conversation
responsemimetype responseschema responsejsonschema schema jsonschema
```

Gemini 扩展 `generationConfig` 时必须使用这个准确拼写，值必须是对象；其中的输出限额与结构化输出保留字段仍不能覆盖。项目没有默认向所有服务发送温度等可选参数，使用前应核对实际服务支持情况。

### 5.2 模板默认关闭思考，怎样主动打开

项目的 DeepSeek 示例明确发送 `thinking.type: disabled`。这是**项目模板的选择**，不能理解为 DeepSeek 服务本身默认关闭思考。已核对的[官方思考模式说明](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)接受 `enabled` / `disabled`；该服务文档当前描述其默认思考开启。

要在现有 Chat profile 中主动开启，在“设置 → 对应配置 → 高级参数 → 扩展请求参数”中保留其他需要的参数，将思考项改为：

```json
{
  "thinking": {
    "type": "enabled"
  }
}
```

手动编辑 YAML 时，对应写法为：

```yaml
extra_body:
  thinking:
    type: enabled
```

保存后完全退出并重新打开应用。需要同时保留 `enabled: true` 的 profile、全局 AI 开关、有效模型 ID 与密钥；只改思考参数不会开启全局 AI。该扩展适用于支持它的服务与协议，不要直接搬到其他厂商或 Responses / Anthropic / Gemini profile。

项目 Chat 适配器只读取最终 `content`，不把 `reasoning_content` 作为知识草稿或正文展示。开启思考后仍要求最终结果满足严格业务 JSON 校验；思考耗时与输出限额应按实际服务和预算核对。超时、空内容、拒答、截断或输出格式错误都明确失败，不自动再次调用。

## 6. 密钥引用、共用与网页保存

下面展示命名关系，不包含可用密钥：

```dotenv
MEMORY_OS_AI_ENABLED=false
MEMORY_OS_AI_KEYS__DEEPSEEK="在本机填写自己的密钥"
```

```yaml
api_key_ref: deepseek
```

`MEMORY_OS_AI_KEYS__` 后面的名称映射到 `api_key_ref`，大小写不敏感。它不是 profile ID 的自动推导：例如 profile ID 为 `deepseek-fast` 时，仍可以引用 `deepseek`。文本与 Embedding 引用同一密钥字典。

同一引用可供多份配置共用。更新该引用的密钥，会在下次启动后影响所有共用它的文本及 Embedding 配置；删除 profile 不会自动删除密钥。要隔离不同账户或用途，给它们不同引用。

`__` 是 Settings 的嵌套分隔符。新的网页密钥更新引用除了满足 `[a-zA-Z][a-zA-Z0-9_-]{0,63}`，还**不能包含连续两个下划线**；例如用 `deepseek_work`，不要用 `deepseek__work`。否则可能被解释成多层结构。旧版已有 YAML 引用或整个 JSON 密钥字典中含 `__` 的记录不会被网页擅自删除，但不应继续按这种方式新增分项环境变量。

也支持整个字典的形式，例如 `MEMORY_OS_AI_KEYS` 中放 JSON 字符串；同名的 `MEMORY_OS_AI_KEYS__...` 分项优先覆盖对应项。常规使用建议选分项形式，便于核对 Compose 的透传列表，不要在 YAML 中写密钥，也不要把密钥塞进 `base_url`、查询参数或 `extra_body`。

网页“保存设置”的实际行为：

1. 写入个人文本 YAML，以及 `.env` 中的 AI 开关、默认配置和明确填写的新密钥；不修改业务数据或 RAG 设置。
2. 密码框初始为空，留空保留已有值；本版没有网页清空或删除已有密钥的操作。全空白的新值也按保留处理。
3. 新密钥最多 8192 字符，拒绝控制字符、DEL、`${` 插值开头和无效 Unicode；密钥不回传，保存成功清空密码框。
4. 用读取时的 revision 检查并发修改。遇到 409 保留输入，先核对最新文件，再决定是否重新读取；不会自动覆盖外部更改。
5. 采用可恢复的两文件写入记录；成功后清理临时凭证备份。保存不调用模型、不热加载；需要重启时询问“现在重启／稍后”。只有 EXE 可在确认后自动正常重启，Python／Docker 显示手动指引。等待重启时，“当前 AI 状态”和表单里下次启动的状态可以不同。

### 6.1 Prompt 模板与单次生成参数

Prompt 模板保存在 SQLite，不属于 YAML／`.env` 模型配置，在独立 Prompt 中心增改、复制、设默认、归档及预览。名称最多 200、描述 2,000、正文 100,000 字符；笔记解析支持输出协议 1／2，知识库问答使用独立的引用输出协议。保存立即供新任务选择，无需重启；提交任务冻结模板版本与内容快照。

模板用途为 `knowledge` 或 `rag_qa`，创建后不可变，每类独立默认。生成页和问答页按用途选择；API 拒绝混用。问答可定制风格与重点，固定的引用、逐字摘录、依据不足与 JSON 校验仍有效。问答返回所选模板 ID、版本及 hash，不新增问答历史。

内置深度模板完整保留用户提供的八阶段中文 Prompt，默认使用 v2 完整 Markdown 正文和逐来源原文引文。固定业务约束另行传递，明确本版无联网工具，关键事实不确定时标记待验证。旧简要模板与旧单篇接口维持 v1。

新页面深度生成预填 `max_output_tokens=16384`、`timeout_seconds=180`，只覆盖该任务，不改所选模型的思考模式及其他 profile 参数。合法范围沿用模型配置的输出／超时约束；不等于供应商必然支持相同上限。合并最多 20 篇，总正文仍受 `AI_MAX_INPUT_CHARS` 限制，逐篇分别检查。

任务保存不含密钥，执行时通过原引用解析当前密钥。暂停后若模型、地址或其他配置已变化，会阻止继续并要求处理配置差异；不会静默切换服务。取消／重启仅阻止下一调用，当前调用收尾，付费失败不自动重发。更多操作见[中文手册 AI 草稿](../readme-cn.md#drafts)。

进程环境变量管理的开关、默认项和密钥不能在网页中覆盖。需要在启动环境中修改后重新启动。网页密码不会进入 localStorage / sessionStorage，普通 GET 和保存响应只返回引用及“已配置”状态；`.env` 和恢复中的临时配置记录仍包含明文凭据，应按私人文件保管。

## 7. Embedding YAML：全部字段与维度语义

也可在设置的 RAG 分区编辑同样参数、默认项、Qdrant URL 和开关。`GET/PUT /api/v1/settings/rag` 采用同源、配置令牌、revision 和二文件事务保护；与 AI 设置共用 `.env` 时会检测并发修改，保留其他字段、密钥及原文输入限制。模型配置保存后需重启，桌面重启入口使用 `scope=rag` 核对对应 revision。Docker 仍由宿主机配置。

`POST /api/v1/settings/rag/test` 为用户主动检测：Qdrant 仅读取版本；Embedding 要求 `confirm_embedding=true`，只发一次短文本，不写向量缓存、笔记或索引。配置变化后旧 revision 不再允许测试；失败不自动重试。预检的 `network_checked=false` 表示只检查本机参数，不能当成服务连通或质量通过。

Embedding 使用独立的 [公开模板](../config/embedding-providers.example.yml)，与生成模型分开配置。模板默认选择本地免密示例 `local`，其模型名 `your-local-embedding-model` 是占位值，必须按真实服务修改；模板本身不会启动或下载模型。

```yaml
schema_version: 1
default_profile: local
profiles:
  local:
    label: 本地向量服务
    enabled: true
    protocol: openai_embeddings
    base_url: http://127.0.0.1:8080/v1
    model: your-local-embedding-model
    dimension: 1024
    auth: none
    batch_size: 8
    timeout_seconds: 60
```

顶层仍为整数 `schema_version: 1`、可空 `default_profile` 和最多 100 个 `profiles`。profile ID 的规则与文本配置相同；一次索引代次只使用选定的一套 Embedding 配置。

| profile 字段 | 默认值／是否必填 | 范围与作用 |
| --- | --- | --- |
| `label` | `null` | 可选显示名；非空时 1–200 字符，不能只有空白或控制字符 |
| `enabled` | `true` | 是否允许使用该向量配置；还需全局 RAG 开启 |
| `protocol` | `openai_embeddings` | 当前仅支持此协议；请求为 `POST <base_url>/embeddings` |
| `base_url` | 必填 | HTTP(S) 地址前缀，1–2048 字符；地址安全校验与文本配置一致，末尾 `/` 去除 |
| `model` | 必填 | 1–200 字符，真实向量模型 ID |
| `model_revision` | `null` | 可选、1–200 字符的模型版本标识；参与索引指纹，不自动发送成上游 API 参数 |
| `dimension` | 必填 | 整数 `1–65536`；预期返回向量的维度，同时决定 Qdrant collection 维度 |
| `api_key_ref` | `null` | 引用同一 `MEMORY_OS_AI_KEYS` 密钥表；格式与文本配置一致 |
| `auth` | `bearer` | `auto` / `bearer` / `x_api_key` / `x_goog_api_key` / `none`；注意其默认值不是文本的 `auto` |
| `request_dimensions` | `null` | 可选整数 `1–65536`，设置后必须等于 `dimension`；仅此时才向上游发送 `dimensions` |
| `timeout_seconds` | `60.0` | `0.01–600` 秒；单批完整请求时限 |
| `batch_size` | `8` | 整数 `1–8`；每批最多输入块数 |
| `extra_body` | `{}` | 受限 JSON 对象；最多 12 层、序列化校验长度 32768，要求有限数值 |

三个容易混淆的字段：

- `dimension` 是**验证期望值**，不是自动降维。服务返回不同维数会失败，不能靠改它把旧向量变成新维数。
- `request_dimensions` 是可选的**请求参数**。只有服务与模型支持显式维数参数时才填写，并与 `dimension` 相等。省略时不会发送 `dimensions`。
- `model_revision` 是应用用于区分语义版本的**本地版本标识**。它不会把服务端模型固定到某版本；应先在服务端选定或部署模型，再用该字段记录变化并触发新代次。

请求总是发送 `encoding_format: float`。结果会校验数量、输入索引、重复索引、维度、有限数值和非全零向量。单次响应最多 16 MiB；错误不自动重新调用付费接口。

Embedding 的扩展参数不能覆盖以下保留名，检查同样递归、忽略大小写和分隔符：

```text
model input encodingformat dimensions stream headers apikey authorization
authentication auth token credentials accesstoken bearertoken
```

Embedding 语义指纹包括 `protocol`、`base_url`、`model`、`model_revision`、`dimension`、`request_dimensions` 和 `extra_body`，再与分块规则组合为索引配置。修改这些内容需显式重建；仅更换密钥、显示名、鉴权方式、超时或批大小不改变这份语义指纹。若服务在相同模型名后静默换模型，应用无法自行识别，需自行更新 `model_revision` 并重建。

### 7.1 本机 Ollama＋BGE-M3 配置

Windows 桌面与本机 Python 接入本地 Ollama 时，使用以下 profile；保留其他已有配置。它与 DeepSeek 文本生成配置独立，不需要向量 API 密钥：

```yaml
schema_version: 1
default_profile: local_bge_m3
profiles:
  local_bge_m3:
    label: 本地 BGE-M3
    enabled: true
    protocol: openai_embeddings
    base_url: http://127.0.0.1:11434/v1
    model: bge-m3
    model_revision: "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
    dimension: 1024
    auth: none
    batch_size: 1
    timeout_seconds: 180
    extra_body: {}
```

此处省略 `api_key_ref` 与 `request_dimensions`，表示不传鉴权头和降维参数。模型的实际 1024 维必须经过一次显式测试核对；`base_url` 不重复包含 `/embeddings`。BGE-M3 的模型规格和无需查询指令前缀说明见 [FlagEmbedding 开源文档](https://github.com/FlagOpen/FlagEmbedding/blob/master/research/BGE_M3/README.md)，接口映射见 [Ollama 兼容说明](https://docs.ollama.com/api/openai-compatibility#v1embeddings)。

配套运行值为 `MEMORY_OS_EMBEDDING_DEFAULT_PROFILE=local_bge_m3`、`MEMORY_OS_RAG_QDRANT_URL=http://127.0.0.1:6333`。先保存为 `MEMORY_OS_RAG_ENABLED=false`，主动检查 Qdrant 与 Embedding，两项通过后再开启并重启。设置页面会维护对应项；手动编辑时不要覆盖其他 AI、密钥和输入限制。

本机固定便携目录已完成上述准备并开启 RAG，当前 `MEMORY_OS_RAG_ENABLED=true`，2 篇现有知识笔记全部发布、无失败或待处理项，正常重启后仍可检索。这是本机个人配置的实际状态，应用代码和公开发行模板的 RAG 默认值仍为 `false`。

示例中的 `model_revision` 是 2026-10-18 下载并核对的 `bge-m3:latest` 完整 digest，实际返回 1024 维；记录本次权重身份，不会让 Ollama 自动锁定标签。其他电脑安装后应核对自己的 `/api/tags`，更换 digest 后更新 revision 并重建。`batch_size=1`、`timeout_seconds=180` 为此次本机方案的配置值，通用默认仍是批次 8、超时 60 秒。此次运行上下文为 4096 tokens，模型元数据的 8192 tokens 不是当前运行上限。

Ollama 的 `OLLAMA_MODELS` 是 **模型服务环境变量**，不是 Memory OS Settings。本机用户值指向 `D:\VsCode\PersonalAiMemoryOs\.cache\ollama\models`；修改后重启 Ollama。独立程序位于 `.tools/ollama/`，不加入全局 PATH、不自动随 Windows 启动；配置下一节的桌面自动准备后，双击 EXE 即可准备服务，手动脚本保留作源码部署或排错入口。安装、日常启动、日志和索引验证的完整操作见 [RAG 指南](rag-guide-cn.md#33-本机方案ollamabge-m3)。

当前 EXE 使用上述宿主机地址；Docker API 的 `127.0.0.1` 指容器自身，不能直接照抄。若另行让 API 容器连接宿主机 Ollama，须单独确认服务监听范围和容器网络可达性。本机部署保持仅本机访问，不为此放开监听到局域网。

桌面自动准备为当前应用进程的 `NO_PROXY` 合并 `localhost,127.0.0.1,::1`，保留已有例外，避免本机 Ollama/Qdrant 请求被系统代理处理；不修改全局代理或用户环境。该值不属于 Memory OS Settings，也不写入模型 YAML。出现“直连正常、桌面报 502”时先确认使用更新后的 EXE 并正常重启；源码进程需自行配置本机例外。

本地 Embedding 和 Qdrant 不产生云端向量服务费用；DeepSeek 引用问答仍可能计费，且会收到问题及选中的知识片段。保存设置、查看状态和语义搜索不等于调用 DeepSeek。真实问答由用户主动提交，本地接口验证不代替生成质量验收。

### 7.2 桌面本地服务自动准备

当前固定安装已配置并实测通过自动启动，直接双击原 EXE 即可，无需执行命令。可选配置文件位于 **EXE 同级运行根目录下** 的 `config/local-rag-startup.json`：

```json
{
  "schema_version": 1,
  "enabled": true,
  "project_root": "../.."
}
```

| 字段 | 作用 |
| --- | --- |
| `schema_version` | 配置格式版本，当前为整数 `1` |
| `enabled` | 是否允许桌面准备本机服务；通用发行包默认不启用 |
| `project_root` | 相对 EXE 目录解析的项目根目录；当前固定安装位置使用 `../..` |

当此配置启用、应用 RAG 已开启、默认 Embedding 指向本机 `11434/v1`、Qdrant 指向本机 `6333` 时，EXE 隐藏调用打包脚本并传入解析后的 `-ProjectRoot`。等待已有 Ollama、Docker Desktop 与 Qdrant 就绪后才继续打开工作台；不会启动另一份 Memory OS、自动下载模型或调用 DeepSeek。

准备失败可选择本次 RAG 关闭后继续基础管理，保存配置仍保持原值，下次启动再次尝试。150 秒等待超时不强杀服务；关闭桌面保留共享 Ollama 和 Qdrant。通用 ZIP 不包含模型权重、Docker Desktop 或本机个人启动配置；复制到其他电脑后应重新准备依赖和项目位置。

此配置只控制桌面启动，不改变 Embedding 语义指纹，不要求数据库迁移。`scripts/start_local_rag.ps1` 仍是手动排错入口，日常使用无需执行 PowerShell；源码和 Docker API 启动不读取它来准备桌面服务。

本次实际 EXE 验收覆盖系统代理下的本机连接、重复启动复用及正常重启，0 次模型调用；固定目录原地升级保留既有配置、业务记录与全部知识文件，索引仍为 2 篇发布、0 失败。全量测试为 1135 项通过、3 项 Windows 符号链接测试跳过及 1 项既有警告。通用发行 ZIP 继续默认不启用本机自动准备。

## 8. 哪些开关需要一起打开

| 目标 | 必需配置 | 是否自动调用模型 |
| --- | --- | --- |
| 资料、笔记管理与导入 | 正常数据库；Markdown 自动同步另需同步开启 | 不调用 |
| 单篇草稿生成 | `AI_ENABLED=true`、启用且就绪的文本 profile | 只有主动生成才调用 |
| 自动增量索引 | `RAG_ENABLED=true`、启用且就绪的 Embedding profile、可用 Qdrant | **启动后立即开始对账**；符合条件的待索引笔记可能触发 Embedding |
| 语义搜索 | RAG 可用、兼容且可用的索引 | 主动搜索可能调用查询 Embedding；不需要 AI 总开关 |
| 引用问答 | RAG 可用，以及 AI 总开关和文本配置就绪 | 主动提问执行检索；有有效依据时才调用生成模型 |

只开启 profile 不会绕过全局开关；反过来，只开启全局开关也不能补齐密钥、模型、维度和服务。默认 AI/RAG 都关闭。DeepSeek 文本生成就绪不代表它提供本项目所需的 Embedding 服务。

开启 RAG 本身可能产生向量服务用量，不能把“保存 AI 设置不会调用模型”扩展为“任何配置生效都不会调用模型”。重建、首次索引、显式重试失败项及主动查询也可能产生用量；故障恢复和缓存复用的边界见 [RAG 指南](rag-guide-cn.md)。

## 9. Docker 的特殊规则

Compose 中没有 `env_file: .env` 把整份配置送入容器。宿主机 `.env` 主要用于 `${...}` 展开，只有 `environment` 已声明的项才会注入。以下两种情况不能仅靠修改 `.env` 实现：

- 增加自定义密钥引用 `my_provider`：需在 Compose 的 `api.environment` 明确增加 `MEMORY_OS_AI_KEYS__MY_PROVIDER` 的透传；或选择已有且合适的引用。
- 修改 `RAG_CHUNK_CHARS` 等“未传入”项：需显式增加对应 environment；修改 `SYNC_INTERVAL` 等“固定”项则需修改当前固定值或改成明确的变量透传。

例如新增引用时，先在宿主机 `.env` 保存密钥，再在 `api.environment` 中增加：

```yaml
MEMORY_OS_AI_KEYS__MY_PROVIDER: "${MEMORY_OS_AI_KEYS__MY_PROVIDER:-}"
```

不要把真实值直接写进 Compose。完成必要配置后，在项目根目录显式重新创建 API 服务，使新的容器环境生效：

```powershell
docker compose up -d --force-recreate api
```

普通 `docker compose restart api` 不会刷新既有容器的环境变量。修改文档示例不等于修改个人 YAML，修改 `.env.example` 也不等于修改个人 `.env`。

当前 Compose 把 `./config` 作为只读目录挂载，且设置 `MEMORY_OS_CONFIGURATION_READ_ONLY=true`；Docker 的设置页面供查看，需在宿主机修改文件。不要仅把只读开关改为 `false` 就尝试网页写入挂载目录。

容器内 `127.0.0.1` 指向容器自身，不能直接沿用宿主机本地模型地址。应填写从 API 容器实际可达的模型地址。Qdrant 的 Compose 地址已经固定为 `http://qdrant:6333`，宿主机本机服务与 EXE 才通常使用 `http://127.0.0.1:6333`。

## 10. 安全保存、状态核对与常见误区

个人 `.env`、个人模型 YAML、业务数据库、Markdown 和配置事务文件不属于发行包或版本控制内容。`.env` 及其完整目录备份含明文凭据；不要上传、贴到聊天或当作普通问题报告分享。展开后的 `docker compose config` 等输出可能包含环境密钥，也不要直接公开粘贴。

EXE 日志在 `logs/memory-os.log`，按 2 MiB 轮转，最多保留 3 个备份。桌面日志会对已加载密钥做替换，并避免保留提供方与配置异常的原始异常文本；业务设置错误使用安全错误码。此机制不能代替私人文件保护，也不意味着任意第三方调试工具的请求头日志都已脱敏。

配置核对可查看：

| 入口 | 能说明什么 | 不能据此断言什么 |
| --- | --- | --- |
| 设置页面 / `GET /api/v1/settings/ai` | 下次启动配置、当前启动状态、环境托管项、实际目录、是否待重启 | 不验证模型连通与质量，不回传密钥 |
| `GET /api/v1/ai/profiles` | 当前已加载文本配置及本地密钥就绪情况 | 不证明账户余额、模型权限或真实调用成功 |
| `GET /api/v1/rag/embedding-profiles` | 当前已加载向量配置及预期维度 | 不证明向量服务可达或语义检索质量 |
| `GET /api/v1/rag/index/status` | 本地索引代次、进度、错误与排除项 | 不是独立的模型连通性探测 |
| `GET /health` | 既有应用与数据库健康合同 | 不包含 AI、Embedding 或 Qdrant 健康保证 |

设置读写仅供本机同源工作台；写入接口还校验 Origin、配置令牌和 revision。这不是账号登录或公网访问控制，不应把当前无登录应用直接暴露到公网。

常见问题的对应处理：

| 现象 | 先核对 |
| --- | --- |
| 网页保存了，但当前仍显示 AI 关闭 | 是否只是保存下次启动值；完全退出再打开，或重建容器；检查环境变量覆盖 |
| profile 已启用，仍无法生成 | 全局 AI、正确默认项或显式选择、密钥引用、模型 ID；`configured` 不等于实际服务可用 |
| 本机可用，Docker 缺密钥 | 新引用是否加入 Compose 明确透传，并重新创建容器 |
| `/chat/completions/chat/completions` 或类似 404 | `base_url` 应填地址前缀，避免重复写完整接口；版本路径需自行核对 |
| `rag_rebuild_required` | 向量模型、revision、地址、维数、扩展或分块配置已变化；确认预算后显式重建 |
| `embedding_response_invalid` | 服务返回数量、索引、维数或数值是否符合协议；不要只改期望维度掩盖实际差异 |
| 开启 RAG 后出现 Embedding 请求 | 后台索引按设计会自动对账；若暂不允许调用，保持 RAG 关闭 |
| 想调端口却无效 | 端口不由 `MEMORY_OS_PORT` 控制；分别检查 Uvicorn、Compose 映射或 EXE 随机端口 |

本页列出的上限是应用允许范围，不保证供应商接受相同范围。没有实际配置和调用预算时，应保持 AI/RAG 关闭；工程模拟验收与真实模型质量验收分别记录。
