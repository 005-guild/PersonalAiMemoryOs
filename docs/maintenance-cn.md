# 维护、恢复与验收手册

## 0.12.0 阅读书架验收（2026-11-15）

`scripts/verify_reading.py` 在 `.cache/reading-verification/` 创建独立的 35 篇合成收藏，关闭 AI/RAG/同步，验证主题、筛选、分页与滚动返回、完整长文、原文、键盘读图及窄屏。脚本比较浏览前后数据库内容，检查无浏览写请求或外部请求；不读取正式密钥或调用模型。需要现有测试依赖和缓存的 Playwright Chromium；冻结模式还需要 Windows WebView2 与本次干净构建目录。

```powershell
uv run --locked python scripts/verify_reading.py
uv run --locked python scripts/verify_reading.py --bundle .cache/desktop-build/4ad272d458894840915bbbffd20a4b2e/dist/PersonalAiMemoryOs
```

第二条的构建路径应替换为本次产物。它复制干净包到隔离目录，验证真实 EXE 的阅读与正常关闭／重开。截图及报告保存在独立验收目录，不打包私人收藏；真实收藏的读取性能需另在只读副本核验，不由合成数据结果推断。

## 0.9.0 检索与本地重排验收（2026-10-19）

应用为 0.9.0、数据库为 0006，既有向量无需重建。以下命令是维护验收入口，日常仍双击固定目录 EXE。缓存中的模型权重和校验清单属于运行依赖，不随旧构建一起清理。

```powershell
uv run --locked python scripts/verify_v09.py --mode local
uv run --locked python scripts/verify_v09.py --mode desktop --bundle .cache/desktop-build/d839abe7d35c40c381fcea05125d09f2/dist/PersonalAiMemoryOs
uv run --locked python scripts/verify_desktop_local_startup.py --rerank --bundle .cache/desktop-build/d839abe7d35c40c381fcea05125d09f2/dist/PersonalAiMemoryOs
uv run --locked python scripts/benchmark_retrieval.py --baseline .cache/capacity-baseline/466c80ace32e4ea68c244f95ea97fcfd
```

构建目录和基线参数应使用本次实际产物。浏览器验收使用真实本地 BGE-M3／TEI 与隔离 Qdrant、模拟生成服务；自动服务验收不调用模型。容量工具复制已停止的合成基线库，只比较旧／新检索，不重新衡量首次索引吞吐，也不将合成向量计时说成 BGE/重排耗时。新路径的向量缓存列读取次数必须为零。

已测：100 篇旧检索中位 708ms，新检索 104ms；1,000 篇分别为 6,520ms 和 237ms。开发机器观测，样本数旧 3／新 5，不是生产性能承诺，首次索引性能问题仍待后续处理。报告：`.cache/retrieval-capacity/ef8d2391b35a4e2f9803f0248f6cb90e/report.json`。

本轮真实问答预算已用完：DeepSeek `deepseek-flash` 共 3 次、输入 10,212／输出 456 tokens，三份自编短笔记的主题概览、依据不足和资料内指令测试均通过逐字引用与语义审阅。报告：`.cache/v09-real-qa/543a28e68a5d435c890f61f82d490d7a/report.json`。调用前记录意图，失败也占预算；持久账本 `.cache/v09-real-qa-budget.json` 会阻止再次自动执行。不得删除账本以重发，也不得把这三个样例当作全部主题、长文、多来源或八阶段草稿质量已验收。

真实调用命令 `scripts/verify_v09_real_qa.py --approved-three-calls` 仅是本轮已授权验收的可审阅入口，不进入默认检查或 CI。当前账本非空时拒绝继续。后续真实模型验收需另定预算，不沿用剩余次数。

本手册对应 `docs/project-audit-cn.md` 的 NEXT-01～07。维护脚本在项目根目录执行，报告进入 `.cache`；不会作为普通启动前提。

## 日常检查

```powershell
uv sync --locked --group desktop
uv run --locked python scripts/check_project.py
```

入口依次检查锁文件、文档链接和示例、Python 回归、网页 JavaScript。Node.js 未安装时明确跳过网页语法检查；CI 使用 `--require-node`，缺失则失败。检查不请求模型、不读取个人配置、不启动 Docker；Windows 桌面依赖单独安装。完整浏览器、Docker、EXE 和真实模型验收仍按各自前提执行，不能用单元测试替代。

文档单独检查：`uv run --locked python scripts/check_docs.py`。它不依赖旧 `.cache`。可选 `--check-build` 用于比较最近一次本地干净构建指纹，此时才需要 `.cache/desktop-build-result.json`。

`.github/workflows/check.yml` 在推送、PR 或手动触发时执行同一检查；仅只读仓库权限、不带模型密钥。工作流提交到本地不等于已在 GitHub 实际运行。

## 实际 EXE 与外部服务复用

```powershell
uv run --locked python scripts/verify_desktop_local_startup.py --bundle <干净构建目录>
```

需要 Windows、WebView2、Playwright，以及已在运行的本机 Ollama/BGE-M3 和 Qdrant。脚本创建隔离空库便携副本，验证启动、系统代理绕过、重复实例、受保护的应用重启、配置保留和退出释放；不会重启 Windows。仅清理隔离库所有权匹配的 collection，不停止共享服务。报告在 `.cache/desktop-local-startup/<编号>/`。模型 revision 从实际安装的 BGE-M3 读取，不依赖旧 PID 或旧报告。

应用重启和系统冷启动分别记录。当前用户要求不重启电脑，冷启动只能准备核验工具，不能标记实测通过。

## 质量、保留与发布边界

真实生成和问答需要固定样例、可追溯引用及人工审阅；默认检查永不调用付费模型。许可证暂保留现状，公开可见不代表已提供开源授权。任何依赖扫描只代表扫描时所用漏洞库的结果，不代表永远无漏洞。

不递归清空 `.cache`：其中包含在用模型、服务日志及恢复证据。先做只读空间盘点，再按明确保留策略处理历史构建和备份；恢复正式数据、删除备份、修改外部服务归属均需另行操作。


## 隔离恢复演练

```powershell
uv run --locked python scripts/verify_recovery.py
```

需要本地 BGE-M3 和 Qdrant。仅使用隔离自编资料，先停止应用，再备份并核验数据库、完整知识目录和配置清单。恢复到全新目录，首次以 AI/RAG 关闭模式启动；之后验证 SQLite 向量缓存重建及语义检索。不会恢复或覆盖正式安装，也不调用 DeepSeek。

2026-10-18 实测通过：`.cache/recovery-validation/08b3e7c22a0745c8a213ff7b4b6fda8d/report.json`。全部数据库记录、多来源关系、知识文件、同步身份和配置哈希保留。缓存恢复零重新向量化，确认搜索使用本地 Embedding。13 个测试覆盖篡改、路径越界、Windows 设备路径、重复键、缺失配置或标记、未登记文件，以及非空模板／中断草稿／暂停任务恢复后不自动调用模型。Windows 目录发布前显式关闭 SQLite 连接。

底层 `scripts/recovery_support.py` 要求目标不存在；映射为 `data/memory.db`、`knowledge/`、`.env` 和 `config/`。自定义路径须另行设计映射。失败保留隔离 staging，工具不自行启动应用。本轮验证缓存重建路线，不宣称 Qdrant 快照恢复已实测。正式恢复仍需单独停机、备份和回退计划。

## 真实质量审阅准备

```powershell
uv run --locked python scripts/prepare_quality_review.py
```

固定输入位于 `examples/quality/retrieval-cn.json`：6 篇自编笔记、10 个检索问题、4 个问答审阅题。准备命令复制输入并记录 SHA-256，生成审阅清单；不读取密钥、不调用模型。草稿审阅覆盖八阶段、忠实度、逐字依据、事实与推论区分、联网能力边界；问答审阅覆盖跨笔记、依据不足和资料指令。

实际生成、回答、运行 ID、用量和人工判断尚未填入，结果明确为 `not_run`。TASK-004／005 的真实生成质量继续待验收。不要因准备工具成功或固定检索命中成功而将它们标记完成。付费调用仍单独安排预算，不自动重试。

## Windows 冷启动核验

```powershell
uv run --locked python scripts/cold_boot_check.py
```

该命令只记录本次 Windows 启动时间、应用／服务就绪、索引代次、模型 revision 和配置哈希，不调用 Embedding。2026-10-18 已保存基线，未重启电脑；基线时用户桌面未运行，记录了该状态。

以后由用户自行重启并直接双击原 EXE，待应用就绪后执行：

```powershell
uv run --locked python scripts/cold_boot_check.py --verify <上次基线报告路径>
```

同一次 Windows 启动只能得到 `pending`；新启动仍需核对模型、配置和索引状态，并人工确认没有先执行准备命令。工具不会把服务探测当成检索质量验收。

已补充隔离目录整体移动后相对 `project_root` 仍有效、旧绝对路径和缺失资源被拒绝的测试。完整本地栈实际搬迁仍未执行：模型权重、存活服务的绝对路径记录和 Compose 命名卷都需要单独处理。不得把目录绑定测试写成整栈搬迁通过，也不会为了该项停止正在共享的正式服务。

## 磁盘盘点和日志保留

```powershell
uv run --locked python scripts/storage_inventory.py
uv run --locked python scripts/rotate_external_logs.py
```

两个命令默认只读，不删除数据。空间盘点只查文件元数据，不打开正文或密钥，不跟随链接／目录联接。报告在 `.cache/storage-inventory/`，分类区分运行依赖、个人数据、发行目录、历史构建、验收证据和未知文件。模型权重与服务记录所在 `.cache/ollama/` 属于受保护运行资料。

保留规则：至少 3 份经过核验的完整备份；保留全部未完成升级／恢复记录；历史构建保留当前引用及最近两份通过验收的构建；验收保留最近成功和未解决失败，30 天后才评估归档。未知文件默认保留。没有自动删除业务记录、草稿、备份或历史产物的功能。

普通桌面日志已有 2 MiB／3 份轮转。外部启动与 Ollama 日志可在相应程序正常退出后显式执行：

```powershell
uv run --locked python scripts/rotate_external_logs.py --apply
```

仅处理三个固定日志，超过 8 MiB 才保留至多 3 份历史日志；检测进程仍存活、归属不明或 Windows 文件占用时跳过，不停止服务、不强制改名。持续运行的外部服务日志目前仍不实时限额；按盘点结果安排正常维护窗口，不能声称已经有连续轮转。2026-10-18 检查三个日志均在限额内，未进行实际轮转或清理。

## 发布和依赖维护

```powershell
uv run --locked python scripts/check_release.py
uv run --locked python scripts/audit_dependencies.py
```

发布检查离线核对 `pyproject.toml`、FastAPI 和锁文件版本、迁移链头、四个网页 vendor／许可证文件 SHA-256。依赖命令默认只生成公开包清单，不联网。维护工具变动不重新发行 EXE，本轮继续 0.8.0／0006；下次应用行为或打包资源改动至少升级补丁版本，保存 commit、构建指纹、锁文件哈希、ZIP／EXE 哈希及验收报告，避免只凭版本号辨认构建。

显式在线公告检查：

```powershell
uv run --locked python scripts/audit_dependencies.py --online
```

只将锁文件中的公共 PyPI 名称／版本和两个网页 npm 包提交给 [OSV 批量接口](https://google.github.io/osv.dev/post-v1-querybatch/)，不上传源码、配置、业务数据或密钥。网络失败、响应错误或未处理完的分页结果不能记成扫描干净。可选 `--proxy` 只接受无认证的本机 HTTP 代理；不要把个人代理地址写入受控配置。

2026-10-18 已查 48 个包版本组合，结果 `no_advisories_reported`，报告 `.cache/dependency-audit/report.json`。这表示查询时的数据源没有报告对应公告，不保证所有版本都已被充分覆盖，更不代表没有任何漏洞；Docker 镜像、系统、WebView2、原生 DLL 不在此次扫描范围。

维护频率：每月一次公告查询；升级依赖和发布前再查一次。发现公告后先核对依赖组、实际可达路径和受影响版本，再做最小升级、锁文件更新及相关回归；涉及渲染、迁移、生命周期时补浏览器或 EXE 验收。不要无差别升级所有包或自动替换供应商模型。

项目许可证暂不新增，保留现有第三方声明；现有 GitHub 可见性不作为新的项目许可证授权。签名、安装器和自动更新仍不在本轮范围。工作流及本地提交完成后不会自动推送远端，远端 CI 待下次授权推送后实际验证。

## 固定检索集与容量测量

```powershell
uv run --locked python scripts/evaluate_retrieval.py
uv run --locked python scripts/benchmark_capacity.py --notes 100 1000
```

第一项需要本地 BGE-M3 和 Qdrant，以独立空库导入固定 6 篇笔记，执行 10 个中文问题；报告模型 digest、实际运行设备信息、1200／200 分块、top_k=5、Recall@5、MRR@5 和请求耗时。2026-10-18 实测 Recall@5=1、MRR@5=1，报告 `.cache/retrieval-quality/0b7600653c4f432aab0ea4ea5560ab58/report.json`。报告只代表这个小型自编集，不代表任意问题或引用回答的质量。应用停止后仅清理本轮拥有的 collection。

第二项不调用任何模型，使用明确标为合成的 1024 维向量、真实 SQLite 和独立 Qdrant 容器／命名卷；不是 BGE-M3 吞吐测试。记录每组笔记数、1500 字符正文、列表和分组延迟、首次索引、无变化对账、单笔记更新、搜索、SQLite 缓存以及 Qdrant 存储字节。不同规模依次运行，Qdrant 字节同时报告阶段前基数与阶段内总量，不能把后者直接当作该阶段新增占用。

每组结果保存进度；失败报告和隔离 SQLite 保留，清理前校验自有容器和卷标签。默认不下载镜像，缺少 `qdrant/qdrant:v1.19.2` 时明确失败；可先用 `--notes 1` 验证环境。大规模首次索引可能持续数分钟，先做 100／1000 的实测再决定是否进行 10000；不虚构吞吐或响应时间承诺。实际冷／热模型速度与合成向量基线分开记录。

2026-10-18 测量结果，报告 `.cache/capacity-baseline/466c80ace32e4ea68c244f95ea97fcfd/report.json`：

| 项目 | 100 篇 | 1000 篇 |
| --- | --- | --- |
| 首次完整索引 | 14.25 秒 | 972.70 秒 |
| 无变化对账 | 0.51 秒 | 5.04 秒 |
| 单笔记更新索引 | 0.76 秒 | 6.69 秒 |
| 搜索中位／P95（10 次） | 680／714 毫秒 | 6547／6626 毫秒 |
| 笔记列表中位（100 条） | 3.06 毫秒 | 5.61 毫秒 |
| 资料分组中位（100 组） | 2.50 毫秒 | 4.12 毫秒 |
| SQLite 文件 | 7,499,776 字节 | 70,963,200 字节 |
| 缓存向量 JSON | 4,191,028 字节 | 41,703,620 字节 |

硬件为 Ryzen 7 7700、约 32 GB 内存、RTX 4080 SUPER 16 GB，补充记录 `.cache/maintenance-hardware.json`。容量模型是 CPU 上的合成向量，GPU 不参与推理。千篇阶段期间还运行过全量回归和其他开发检查，主机不独占；本结果用于发现瓶颈，下一轮先 profile，再在空闲主机重复关键测量。优先关注索引发布和搜索过滤时的重复全库读取，不能通过取消版本／删除／冲突校验来换速度。

`du -sb` 是文件逻辑大小，包含 Qdrant mmap 预留，不能当成 Windows 实际磁盘占用。补充命令从已停止的合成容量缓存批量上传，不调用模型：

```powershell
uv run --locked python scripts/measure_cached_vector_storage.py --database <容量报告目录>/stage-1/data/memory.db
```

仅接受项目 `.cache/capacity-baseline` 下明确标为合成模型的缓存。独立 1000 篇／2000 点实测：逻辑字节 621,025,786，Linux 文件已分配字节 19,922,944，报告 `.cache/capacity-storage/bcdf7bb1f2734132ba57bd29c343cebe/report.json`。这是运行时卷内采样，不是宿主机 Docker VHDX 总体占用，也不是应用逐篇发布吞吐；测试容器和卷已清理，源缓存哈希保持不变。
