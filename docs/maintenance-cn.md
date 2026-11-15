# 维护、恢复与验收手册

## 历史带图收藏补验

2026-11-15按用户确认，使用历史收藏完成图片同步补验，无需等待远端新增收藏事件。新增维护模式复用现有浏览器、解析器、导出器和磁盘完成账本，不改产品逻辑、数据库结构、模型或预算。固定桌面继续使用0.14.2／0009，无需构建或替换安装。

```powershell
uv run --locked python scripts/verify_zhihu_media.py --suite historical-images
uv run --locked python scripts/verify_zhihu_media.py --suite historical-images --execute
```

第一条仅离线盘点正式同步目标：检查Markdown图片引用、文件可解码性及动画全部帧，记录未引用文件但不删除。它不连接知乎，不调用模型，也不获取桌面互斥锁。第二条需先正常关闭桌面，以互斥锁独占本应用已有登录资料；完成后重新打开桌面。不要同时运行两项真实账号维护验收。

执行模式选取当前在线可访问的历史内容，覆盖回答／文章／想法各自单图、多图，再复用或增加超长图（任一边大于8192像素）和图片为主的回答（正文少于200字）；总计6–8篇，缺少覆盖条件则失败并报告，不用其他场景冒充。首次导出到全新的`.cache/zhihu-media/<随机目录>/articles`，逐项核对所有引用、原始顺序及下载字节哈希，不重编码原图。紧接着重跑并另启独立Python进程重读磁盘账本：均应全部跳过、无正文或图片请求、已发布文件哈希与修改时间不变。此处不要求隔离`.sync`状态文件的元数据保持不变。

故障恢复使用本次实际响应的离线重放，在独立`recovery/articles`中人为令第二张图片失败，验证未发布最终Markdown、未登记完成；恢复后复用已保存正文和第一张图片，只补齐剩余图片，再跑全部跳过。它不人为破坏正式目录，也不把注入失败记作线上产品故障。正式原文及图片、完成账本、整理库镜像、vault、配置、环境文件和SQLite数据库在桌面关闭期间比较前后哈希；报告仅存指纹，不输出密钥。浏览器登录资料和运行日志不纳入逐字节不变约束。缓存路径拒绝符号链接和Windows目录重解析点，防止隔离路径转向正式数据。

本次结果：578篇原文中150篇带图，1321个被引用图片文件、1325个实际文件全部健康，共解码1440帧；4个未引用文件保留。真实7篇／11张图完成全部覆盖，首次新增7、失败0，立即重跑和独立进程均新增0／跳过7；恢复用例续传成功，未再次请求已完成图片或正文。正式数据指纹未变，模型调用0。当前站点可见577篇、3条未返回内容，另1篇历史内容已不在当前可见集合；本次不删除对应本地内容。

证据：`.cache/zhihu-media/78435215452343a1ab8aed3f65c82c85/report.json`，同目录有前后保护指纹、独立进程报告、私有响应缓存及`final-offline-verification.json`。最终路径防护调整后使用同批实际响应再次离线核对，未重复联网下载。新增与既有同步相关65项测试通过（1条既有Starlette警告）。桌面已正常恢复，仍为578 Sources／580 Knowledge／709条整理调用、580篇索引就绪、1903个原始文件保留、月记账4.608940／30元；自动同步再次运行新增0、失败0。私有报告、正文和图片不提交Git。

本次验收明确覆盖历史图片同步；没有观察远端刚加入收藏事件，也不据此声称发生了该事件。按本次用户范围，该事件不再作为图片补验的等待项。Windows物理冷启动与第二台Windows仍需用户安排，继续禁止重启；本工具也不改变已完成条目的跳过语义，人工删除或修改本地完成项不会被自动覆盖修复。下面保留此前版本与验收历史。

## 安全依赖更新与公告复查

2026-11-15按现有“每月及发布前”规则重新查询当前锁文件，共53个公开包版本组合，发现3个受公告影响的依赖。先核对维护者公告、固定版本及本项目使用路径，再作定向更新：

| 包 | 原版本 → 修复版本 | 公告与本项目路径 |
| --- | --- | --- |
| certifi | 2026.7.22 → 2026.10.19 | [维护者公告](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2)：移除受影响的emSign根信任；经HTTPX进入HTTP客户端。采用2026.10.19保留后续恢复的未受影响根。 |
| opentelemetry-api | 1.45.1 → 1.45.2 | [维护者公告](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-mf5v-w3w3-f6cg)：超长含换行traceparent正则解析可能耗时；由FastAPI间接引入，应用未提供MCP入口。仍更新其依赖并验证长度拦截。 |
| setuptools | 84.0.0 → 84.1.0 | [维护者公告](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w)：Windows旧wheel安装路径可受namespace元数据影响；由PyInstaller构建组引入，应用无wheel安装入口。 |

交付版本0.14.2，schema仍0009，仅这三项依赖和应用版本变化。按[uv约束规则](https://docs.astral.sh/uv/reference/settings/#constraint-dependencies)设置传递依赖安全下限，并单独约束setuptools隔离构建版本。此次使用同步后的构建环境重新打包；跳过同步只能复用与当前锁一致的环境。

更新后在线查询53项、受影响0项，报告 `.cache/dependency-audit/report.json`，锁哈希 `ee9491763985ffb9ad2dd91650fe503753d47c163c87d342b0fb106a400a6a0d`。原受影响结果在 `.cache/security-release/audit-before.json`；2026-10旧报告已存 `.cache/dependency-audit/history/`。保存时间与范围，不把“未报告对应公告”等同于不存在漏洞；Docker、OS、WebView2及原生DLL不在本查询范围。

两个直接安全用例通过：CA集合中不再有受影响的emSign ECC根；超长含换行输入在进入正则前被拦截，正常traceparent仍可解析。1369项完整回归、实际冻结EXE及阅读书架通过，729个安装资源校验通过，固定目录已备份后交付0.14.2并打开；源码记录见[任务记录](../IMPLEMENTATION_TASKS.md)。没有模型调用或预算变化。

## 收藏导出与整栈搬迁验收

0.14.1 / 0009 增加以下维护入口。先正常关闭固定桌面，执行真实账号导出验收；登录资料仅由本应用浏览器使用，不提取凭据。

```powershell
uv run --locked python scripts/verify_zhihu_media.py
uv run --locked python scripts/verify_zhihu_media.py --execute
uv run --locked python scripts/verify_stack_relocation.py --bundle .cache/desktop-build/<本次构建>/dist/PersonalAiMemoryOs
```

前两条扫描当前收藏，选取回答、文章、想法各一篇带图片的既有内容；默认仅预览。`--execute` 首次导出到新的 `.cache/zhihu-media/<随机目录>/articles`，重复运行同一批验证跳过、文件哈希不变且没有再次请求正文或图片，同时核对正式原文和数据库未变。这不修改远端收藏，也不证明真实“刚加入收藏”事件已发生。私人原文、图片及报告都不提交。

第三条需要 Windows、Docker、`.tools/ollama`、`.cache/ollama/models` 和至少约7GiB空闲空间。它把干净 EXE、82个 Ollama 文件和7个模型文件复制到隔离目录；以真实 BGE-M3 建立三篇合成笔记的索引，下载集合快照并记入校验和，正常关闭后整体移动到中文路径，在新建 Qdrant 卷上传恢复。核对数据库、vault、模型哈希、集合归属、点与向量载荷、同一索引代次及搬迁前后的真实查询，最后仅停止自建服务和清理自建卷。报告保存在 `.cache/stack-relocation/`。依据 [Qdrant 快照接口](https://qdrant.tech/documentation/snapshots/)使用集合快照；不把它当作正式备份工具或跨机器验收。

2026-11-15实测：三类首次各导出1篇及1张图，重复新增0、跳过3；整栈同机搬迁恢复3个点并通过全部查询，正式数据和共享模型未变。证据分别为 `.cache/zhihu-media/3a67df3c4fc741ba9d971531a63de988/report.json` 和 `.cache/stack-relocation/9ff02b90c7c241a686c5cc5b9c9c64e8/report.json`。后者使用已验证的0.14.0干净包验证搬迁流程，0.14.1另行完成发行回归。

用户继续禁止重启，且目前只有此电脑：物理冷启动和第二台 Windows 验收保留待办。`cold_boot_check.py` 只记录和比较，不重启或操作服务。等待用户安排窗口后，直接打开 EXE，再比较重启前后证据并验证实际查询。真实新增收藏的图片、文章及想法导出也保留事件验收边界。主题综述继续由用户手动生成。

Windows 干净检出需保留第三方资源原始 LF；`.gitattributes` 仅为 `app/web/vendor` 固定换行，确保发行完整性校验与上游一致。统一检查失败会输出对应日志末尾，便于远端 CI 定位，不再只显示失败状态。

0.14.1已备份后原地交付，全量1362项通过、3项既有跳过，真实EXE及正式页面通过，代码提交ac99924的Windows远端CI已通过。0.14.1冷启动基线保留；当前0.14.2新基线为 `.cache/cold-boot/da9bd81d02394efe9bcac79d7d90afe6/report.json`。用户自行安排重启并直接打开EXE后，可运行 `uv run --locked python scripts/cold_boot_check.py --verify .cache/cold-boot/da9bd81d02394efe9bcac79d7d90afe6/report.json`，再执行实际查询；该命令自身不重启电脑。

原生“另存为”后续已补验通过，见下面流程。此前 `.cache/native-save-as/b76d04b674864eeea5b7031e56bc03b4/report.json` 保留为输入选择器被工具窗口归属检查拦截的失败记录；本次补验不覆盖该选择器。

## 原生报告保存验收

`scripts/verify_native_save.py`仅准备随机缓存目录并校验文件；原生对话框操作需由操作者或计算机使用工具实际完成。正式安装保持原样，使用0.14.1干净包的副本，关闭AI/RAG/同步，不设置桌面测试模式。仅修改副本index.html并加入合成文件载入JS，EXE、导入／报告模块和原生保存处理器均与干净包一致。

```powershell
uv run --locked python scripts/verify_native_save.py prepare --bundle .cache/desktop-build/<本次构建>/dist/PersonalAiMemoryOs --launch
```

打开新副本的“资料导入 → 载入验收用合成文件 → 预演文件 → 下载报告”。在真正的原生“另存为”窗口，将文件存到该副本 `exports/原生保存报告.json`。不提交导入。以prepare打印的实际目录替换下面路径：

```powershell
uv run --locked python scripts/verify_native_save.py checkpoint-save --evidence .cache/native-save-as/<本次验收>
```

再次点击“下载报告”，在原生窗口将文件名设为 `取消不应创建.json`，点击“取消”，再执行：

```powershell
uv run --locked python scripts/verify_native_save.py verify --evidence .cache/native-save-as/<本次验收> --confirm-native-ui
```

`--confirm-native-ui`只声明操作者已经观察并完成原生保存和取消；不要仅凭文件存在添加此标志。省略时报告为UI待确认，退出码2。工具检查UTF-8 JSON、预演计数、无原文content字段、取消后所有导出文件及哈希保持原样、隔离数据库完整且没有导入Source、正式业务行哈希未变、除测试HTML/JS外程序资源一致。准备拒绝正式安装目录，篡改context不能将校验指向正式runtime；原生输入文件选择器和退出流程另有范围，不能由本工具推导通过。

2026-11-15实际完成保存和取消，报告436字节，正式记录未变，付费调用0。证据在 `.cache/native-save-as/74163155c9324a3bb2f18fdd30095bb3/{save-check,cancel-check,report,verification}.json`。五项路径／上下文保护测试、干净包准备、实际报告校验和fixture语法检查通过。无需再次打包或升级正式EXE。

## 0.14.0 维护增量（2026-11-15）

详细摘要沿用收藏记录和调用账本，主题综述由0009新增的topic_summaries保存派生结果。备份和恢复需包含完整数据库，升级工具已核对0008与0009表结构。先正常退出固定桌面，再使用缓存采纳和分类审核维护命令。

新增scripts/verify_shared_quality.py --allow-paid用于此次已授权的七个固定质量用例，费用通过现有收藏月账本预留，不扩大预算或自动重试。当前试点原始账本保持独立，外部费用元数据只计入对应月份一次。个人审核清单和报告放.cache，不能提交。

新启动的Ollama由scripts/supervise_ollama.ps1隐藏监督读取两路输出，单文件约8MiB、3份轮转。桌面启动准备输出由独立线程读取并持续轮转。当前已运行的旧Ollama在下一次正常启动时采用新监督机制，应用升级不主动停止共享服务。下文的停机轮转仍适用于旧日志。保留策略与只读盘点工具继续管理历史构建和备份。


## 摘要质量试点工具

在项目根目录运行以下命令。准备阶段只读固定安装数据库，挑选 2 篇长文、2 篇图片文章和尽量分散主题的 6 篇普通文章；输出目录必须是 `.cache/summary-quality/` 的子目录，首次准备需使用尚不存在的目录。

```powershell
uv run --locked python scripts/summary_quality_pilot.py prepare --directory .cache/summary-quality/pilot-20261115
uv run --locked python scripts/summary_quality_pilot.py generate --directory .cache/summary-quality/pilot-20261115 --allow-paid
uv run --locked python scripts/summary_quality_pilot.py report --directory .cache/summary-quality/pilot-20261115
```

`--runtime` 默认指向固定桌面 `dist/PersonalAiMemoryOs-0.6.6`；准备读取其 `data/memory.db`，生成通过现有配置解析器在内存中取得默认模型与密钥，不回显、不复制凭据。生成会把选中的私人原文及清晰图片识读文字发送给已配置的 OpenAI 服务。其余收藏不进入请求；样本、结果、原始响应和评价均留在被 Git 忽略的私人缓存中，不随源码提交。

同一试点共用固定 `budget.json` 和独占锁：最多 5 元、10 次生成，生成前计数并持久化预留；失败／中断仍计入预留，不自动付费重试。重复成功请求复用响应。禁止删除账本或锁文件来重置额度；中断后须先核对进程与已保存的意图，不能把未知请求当作未发生。价格沿用既有保守价格快照，实际账单以提供商为准。

打开输出目录的 `report.html` 可离线对照；`report.md` 为完整文本副本。短提要通常 80–180 字，详细部分通常 600–1500 字，按信息量调整。每个要点关联 Q 引文或 O 图片识读编号，Q 必须能逐字回到原文；O 不冒充逐字引文。部分图片无法辨认的提示必须保留。原文或人工笔记变化会停止生成，重新准备不能绕过原试点费用和次数上限。

`review.json` 保存逐篇人工评价：`outcome` 为 `pending`、`improved`、`same`、`worse` 或 `rejected`；`scores` 对“忠实性／完整度／结构／可读性／原文依据”分别给 1–5 分，`notes` 写明理由，`fatal_findings` 记录编造、错误归因等严重问题。编辑评价后运行 `report` 刷新。全部 10 篇完成、至少 8 篇改进且其余不退步、无严重问题，才显示达到推广门槛；这不自动采纳候选，也不自动处理全部收藏。该工具无需升级 EXE 或迁移数据库。

## 0.12.0 阅读书架验收（2026-11-15）

`scripts/verify_reading.py` 在 `.cache/reading-verification/` 创建独立的 35 篇合成收藏，关闭 AI/RAG/同步，验证主题、筛选、分页与滚动返回、完整长文、原文、键盘读图及窄屏。脚本比较浏览前后数据库内容，检查无浏览写请求或外部请求；不读取正式密钥或调用模型。需要现有测试依赖和缓存的 Playwright Chromium；冻结模式还需要 Windows WebView2 与本次干净构建目录。

```powershell
uv run --locked python scripts/verify_reading.py
uv run --locked python scripts/verify_reading.py --bundle .cache/desktop-build/e47a093b825f4fcaa500332557dd10ce/dist/PersonalAiMemoryOs
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

底层 `scripts/recovery_support.py` 要求目标不存在；映射为 `data/memory.db`、`knowledge/`、`.env` 和 `config/`。自定义路径须另行设计映射。失败保留隔离 staging，工具不自行启动应用。上述2026-10-18演练只验证缓存重建；2026-11-15另行完成的整栈演练验证了Qdrant集合快照，见本手册顶部。正式恢复仍需单独停机、备份和回退计划。

## 真实质量审阅准备

```powershell
uv run --locked python scripts/prepare_quality_review.py
```

固定输入位于 `examples/quality/retrieval-cn.json`：6 篇自编笔记、10 个检索问题、4 个问答审阅题。准备命令复制输入并记录 SHA-256，生成审阅清单；不读取密钥、不调用模型。草稿审阅覆盖八阶段、忠实度、逐字依据、事实与推论区分、联网能力边界；问答审阅覆盖跨笔记、依据不足和资料指令。

上述 `not_run` 是2026-10-18准备时的快照。2026-11-15已沿用同一固定语料完成3个八阶段分析及4个引用问答，用真实默认模型生成并对照原文审阅，`.cache/shared-quality/report.json` 的status为passed；费用0.937520元已记入共享月账本。它覆盖这7个固定用例，不能推导任意文章质量。准备工具本身仍不调用模型；后续付费调用沿用显式预算和不自动重试规则。

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

仅处理三个固定日志，超过 8 MiB 才保留至多 3 份历史日志；检测进程仍存活、归属不明或 Windows 文件占用时跳过，不停止服务、不强制改名。旧方式启动的外部服务日志在正常重启前沿用原写入方式；新监督进程提供持续轮转。按盘点结果安排旧服务的正常维护窗口。2026-10-18 检查三个日志均在限额内，未进行实际轮转或清理。

## 发布和依赖维护

```powershell
uv run --locked python scripts/check_release.py
uv run --locked python scripts/audit_dependencies.py
```

发布检查离线核对 `pyproject.toml`、FastAPI 和锁文件版本、迁移链头、四个网页 vendor／许可证文件 SHA-256。依赖命令默认只生成公开包清单，不联网。维护工具首版对应0.8.0／0006，当前发行以顶部记录为准；仅维护工具变动无需重新发行EXE，依赖或程序资源变化需要重新打包；下次应用行为或打包资源改动至少升级补丁版本，保存 commit、构建指纹、锁文件哈希、ZIP／EXE 哈希及验收报告，避免只凭版本号辨认构建。

显式在线公告检查：

```powershell
uv run --locked python scripts/audit_dependencies.py --online
```

只将锁文件中的公共 PyPI 名称／版本和两个网页 npm 包提交给 [OSV 批量接口](https://google.github.io/osv.dev/post-v1-querybatch/)，不上传源码、配置、业务数据或密钥。网络失败、响应错误或未处理完的分页结果不能记成扫描干净。可选 `--proxy` 只接受无认证的本机 HTTP 代理；不要把个人代理地址写入受控配置。

2026-10-18记录为48个包版本组合、`no_advisories_reported`；旧报告已归档在 `.cache/dependency-audit/history/report-2026-10-17-95bb0c8a2919.json`（报告UTC日期17日，本机为18日）。2026-11-15复查和三项定向修复见本手册顶部，当前 `.cache/dependency-audit/report.json` 对应新锁文件。这些结果仅表示查询时数据源的对应公告，不保证所有版本都已被充分覆盖；Docker 镜像、系统、WebView2、原生 DLL 不在此次扫描范围。

维护频率：每月一次公告查询；升级依赖和发布前再查一次。发现公告后先核对依赖组、实际可达路径和受影响版本，再做最小升级、锁文件更新及相关回归；涉及渲染、迁移、生命周期时补浏览器或 EXE 验收。不要无差别升级所有包或自动替换供应商模型。

项目许可证暂不新增，保留现有第三方声明；现有 GitHub 可见性不作为新的项目许可证授权。签名、安装器和自动更新仍不在本轮范围。后续普通变更默认仅本地提交，明确授权后推送；本批已获授权且代码远端CI通过，见最新任务记录。

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
