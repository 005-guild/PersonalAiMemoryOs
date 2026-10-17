import {api} from '../api.js';
import {el, button, notice, badge, empty, pageHeading, formatDate, confirmAction, showError} from '../ui.js';
import {pollVisible, profilesTable, jsonView, details, keyValues} from './workflow-utils.js';
import {conflictsPanel} from './system-conflicts.js';

function counts(value = {}) {return el('div', {className: 'page-actions'}, ...Object.entries(value).map(([name, count]) => badge(`${({published: '已发布', pending: '待处理', failed: '失败', excluded: '已排除', synced: '已同步', conflict: '冲突', error: '错误', deleted: '已删除'})[name] || name} ${count}`)));}

function syncDetails(status) {
  const problems = (status.notes || []).filter(note => note.last_error || !['synced', 'deleted'].includes(note.status));
  return el('div', {className: 'stack'},
    keyValues([['自动同步', status.enabled ? '已开启' : '已关闭'], ['后台任务', status.running ? '运行中' : '已停止'], ['上次扫描', formatDate(status.last_scan_at)]]),
    counts(status.counts), status.last_error && notice(status.last_error, 'error'),
    status.issues?.length > 0 && details(`文件问题（${status.issues.length}）`, jsonView(status.issues)),
    problems.length > 0 && details(`待处理 / 异常笔记（${problems.length}）`,
      el('div', {className: 'table-wrap'}, el('table', {className: 'data-table'}, el('tbody', {}, ...problems.map(note => el('tr', {},
        el('td', {}, el('a', {href: `#/knowledge/${note.knowledge_id}`}, note.path || note.knowledge_id)), el('td', {}, note.status), el('td', {}, note.last_error || '等待同步'))))))),
    !status.last_error && !status.issues?.length && !problems.length && el('p', {className: 'muted'}, '当前没有待处理的文件问题。'));
}

function indexDetails(status) {
  return el('div', {className: 'stack'},
    keyValues([['RAG', status.enabled ? '已开启' : '已关闭'], ['后台对账', status.worker_running ? '运行中' : '已停止'], ['当前任务', status.running ? '执行中' : '空闲'], ['上次对账', formatDate(status.last_scan_at)]]),
    counts(status.counts), status.last_error && notice(status.last_error, 'error'),
    status.enabled && status.index_incomplete && notice('索引尚未完整；检索只使用已发布且仍有效的笔记片段。', 'warning'),
    status.generation ? details('当前索引代次', jsonView(status.generation)) : el('p', {className: 'muted'}, '尚无索引代次。'),
    status.errors?.length > 0 && details(`索引错误（${status.errors.length}）`, jsonView(status.errors)),
    status.excluded?.length > 0 && details(`排除笔记（${status.excluded.length}）`, jsonView(status.excluded)));
}

export async function mount(container, context) {
  const controller = new AbortController(); let stopped = false, syncBusy = false, indexBusy = false, indexState = null;
  const syncBody = el('div'), indexBody = el('div'), configBody = el('div'), syncErrors = el('div'), indexErrors = el('div');
  const conflicts = conflictsPanel(context, {signal: controller.signal, alive: () => !stopped});
  const syncRun = button('立即同步一轮', async () => {
    if (stopped || syncBusy) return; syncBusy = true; syncRun.disabled = true; syncErrors.replaceChildren();
    try {
      await api('/api/v1/sync/run', {method: 'POST'});
      if (!stopped) {syncErrors.append(notice('同步扫描已完成。', 'success')); await Promise.all([refreshSync(), conflicts.refresh()]);}
    } catch (error) {if (!stopped) showError(error, syncErrors);}
    finally {syncBusy = false; if (!stopped) syncRun.disabled = false;}
  }, {'data-testid': 'sync-run'});
  const indexRun = button('更新索引', () => indexAction(false, false), {'data-testid': 'index-run'});
  const indexRetry = button('重试失败项', () => indexAction(true, false), {'data-testid': 'index-retry'});
  const indexRebuild = button('重建索引', () => indexAction(false, true), {'data-testid': 'index-rebuild'});
  function updateIndexButtons() {
    for (const node of [indexRun, indexRetry, indexRebuild]) node.disabled = indexBusy || !indexState?.enabled || indexState?.running;
  }
  async function indexAction(retry, rebuild) {
    if (stopped || indexBusy || !indexState?.enabled || indexState.running) return;
    const message = rebuild ? '将创建新的索引代次并重建，期间检索可能不可用；需要的新向量可能调用收费 Embedding 服务。是否继续？'
      : retry ? '将显式重试失败或结果不明的向量调用，可能再次产生费用。是否继续？'
        : '将扫描已提交笔记并更新索引；新内容可能调用收费 Embedding 服务，不会自动重试既有失败项。是否继续？';
    // The busy flag covers the confirmation as well as the submitted request.
    indexBusy = true; updateIndexButtons();
    try {
      if (!await confirmAction(message, {title: rebuild ? '重建索引' : retry ? '重试失败项' : '更新索引', confirmLabel: '继续执行'}) || stopped) return;
      indexErrors.replaceChildren();
      await api(`/api/v1/rag/index/${rebuild ? 'rebuild' : 'run'}`, {method: 'POST', ...(rebuild ? {} : {body: {retry_failed: retry}})});
      if (!stopped) {indexErrors.append(notice('索引任务已提交。下方状态会自动刷新。', 'success')); await refreshIndex();}
    } catch (error) {if (!stopped) {showError(error, indexErrors); indexErrors.append(notice('未自动重试索引任务。请查看错误后再决定是否手动执行。'));}}
    finally {indexBusy = false; if (!stopped) updateIndexButtons();}
  }
  async function refreshSync() {
    try {const value = await api('/api/v1/sync/status', {signal: controller.signal}); if (!stopped) syncBody.replaceChildren(syncDetails(value));}
    catch (error) {if (!stopped) showError(error, syncBody);}
  }
  async function refreshIndex() {
    try {const value = await api('/api/v1/rag/index/status', {signal: controller.signal}); if (!stopped) {indexState = value; indexBody.replaceChildren(indexDetails(value)); updateIndexButtons();}}
    catch (error) {if (!stopped) {indexState = null; updateIndexButtons(); showError(error, indexBody);}}
  }
  async function loadConfigs() {
    const results = await Promise.allSettled([api('/api/v1/ai/profiles', {signal: controller.signal}), api('/api/v1/rag/embedding-profiles', {signal: controller.signal})]);
    if (stopped) return;
    configBody.replaceChildren(...results.map((result, index) => {
      if (result.status === 'rejected') return notice(`${index ? '向量' : '生成'}配置读取失败：${result.reason.message}`, 'error');
      const value = result.value;
      return el('div', {className: 'stack'}, el('h3', {}, index ? 'Embedding 配置' : '文本生成配置'), badge(value.enabled ? '功能已开启' : '功能已关闭'),
        value.error_code && notice(value.error_code, 'warning'), profilesTable(value));
    }));
  }
  container.append(pageHeading('同步与系统状态', '检查文件同步、解决版本冲突、维护索引，并查看模型配置是否就绪。'),
    el('div', {className: 'grid'},
      el('section', {className: 'card stack'}, el('div', {className: 'detail-header'}, el('h2', {}, 'Markdown 同步'), syncRun), syncBody, syncErrors),
      el('section', {className: 'card stack'}, el('h2', {}, '知识索引'), el('div', {className: 'page-actions'}, indexRun, indexRetry, indexRebuild), indexBody, indexErrors)),
    conflicts.node,
    el('section', {className: 'card stack'}, el('div', {className: 'detail-header'}, el('h2', {}, '模型配置（只读）'), el('div', {className: 'page-actions'}, el('a', {className: 'btn', href: '#/settings'}, '打开设置'), button('刷新配置状态', loadConfigs))),
      notice('“配置就绪”仅表示参数和所需密钥已配置，不代表真实接口连通性或生成质量已验收。本页只展示状态；文本生成配置可在设置中修改。'), configBody,
      details('如何在本机配置', el('div', {className: 'stack'},
        el('p', {}, '文本生成配置：config/ai-providers.yml；向量配置：config/embedding-providers.yml。密钥只写入项目 .env 或环境变量。'),
        el('p', {}, '开关为 MEMORY_OS_AI_ENABLED 与 MEMORY_OS_RAG_ENABLED；修改配置后需要重新启动服务。请按 README 的备份和启动说明操作。'),
        el('p', {}, '正式模型质量验收独立进行；本页面不会启用配置、探测远程服务或触发测试调用。')))));
  updateIndexButtons(); await Promise.all([refreshSync(), refreshIndex(), loadConfigs(), conflicts.ready]);
  const stopPoll = pollVisible(async () => {await Promise.all([refreshSync(), refreshIndex(), conflicts.refresh()]);});
  return () => {stopped = true; controller.abort(); stopPoll();};
}
