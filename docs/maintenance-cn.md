# 维护、恢复与验收手册

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

2026-10-18 实测通过：`.cache/recovery-validation/08b3e7c22a0745c8a213ff7b4b6fda8d/report.json`。全部数据库记录、多来源关系、知识文件、同步身份和配置哈希保留。缓存恢复零重新向量化，确认搜索使用本地 Embedding。12 个测试覆盖篡改、路径越界、Windows 设备路径、重复键、缺失配置或标记、未登记文件。Windows 目录发布前显式关闭 SQLite 连接。

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
