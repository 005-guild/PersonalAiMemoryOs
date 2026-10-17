import {api} from '../api.js';
import {el, button, field, notice, badge, empty, pageHeading, formatDate, showError} from '../ui.js';
import {select, pager, sourcePicker, profilePicker, profileReady, labelStatus, pollVisible, dataTable} from './workflow-utils.js';
import {renderRun} from './processing-detail.js';

export async function mount(container, context) {
  const controller = new AbortController(); let stopped = false, busy = false, source = null, offset = 0, request = 0, detailRunning = true;
  const registry = await api('/api/v1/ai/profiles', {signal: controller.signal});
  const errors = el('div'); const sourceInfo = el('div'); const records = el('div'); const detail = el('div');
  const selectedId = context.params.get('source_id') || '';
  const model = profilePicker(registry); model.dataset.testid = 'processing-profile';
  const status = select([['', '全部状态'], ...['running', 'ready', 'adopted', 'failed', 'interrupted'].map(value => [value, labelStatus(value)])], context.params.get('status') || '');
  status.setAttribute('aria-label', '处理记录状态');
  const generation = button('生成知识草稿', generate, {className: 'btn btn-primary', disabled: true, 'data-testid': 'processing-generate'});
  const picker = sourcePicker(id => {loadSource(id); loadRuns(0);}, {selected: selectedId, includeAll: true, signal: controller.signal});
  picker.node.querySelector('select').dataset.testid = 'processing-source';
  function update() {
    generation.disabled = busy || !source || Boolean(source.deleted_at) || !profileReady(registry, model.value);
    model.disabled = busy;
    for (const node of picker.node.querySelectorAll('input, select, button')) node.disabled = busy;
  }
  async function loadSource(id) {
    source = null; update(); sourceInfo.replaceChildren(); if (!id) return;
    try {
      const value = await api(`/api/v1/sources/${encodeURIComponent(id)}`, {signal: controller.signal});
      if (stopped || picker.value !== id) return;
      source = value;
      sourceInfo.append(el('p', {className: 'muted'}, `${value.title} · v${value.version}${value.deleted_at ? ' · 已删除' : ''}`)); update();
    } catch (error) {if (!stopped) showError(error, sourceInfo);}
  }
  async function generate() {
    if (stopped || generation.disabled || busy || !source) return;
    busy = true; update(); errors.replaceChildren(notice('正在生成草稿，请等待。离开或断开页面后，可在该来源的处理记录中查找结果。'));
    try {
      const payload = {source_id: source.id, expected_source_version: source.version};
      if (model.value) payload.profile_id = model.value;
      const run = await api('/api/v1/processing/runs', {method: 'POST', body: payload});
      if (!stopped) context.navigate(`#/processing/${run.id}`);
    } catch (error) {
      if (stopped) return;
      showError(error, errors);
      const runId = error.detail?.run_id || error.data?.run_id;
      if (runId) errors.append(el('a', {href: `#/processing/${runId}`}, '查看本次失败记录'));
      errors.append(notice('未自动重试。若请求断连，请先刷新该来源的处理记录确认是否已完成，再决定是否发起新调用。'));
      await loadRuns(0);
    } finally {busy = false; if (!stopped) update();}
  }
  async function loadRuns(nextOffset = offset) {
    offset = nextOffset; const sequence = ++request;
    const query = new URLSearchParams({offset: String(offset), limit: '20'});
    if (picker.value) query.set('source_id', picker.value);
    if (status.value) query.set('status', status.value);
    if (model.value) query.set('profile_id', model.value);
    try {
      const page = await api(`/api/v1/processing/runs?${query}`, {signal: controller.signal});
      if (stopped || sequence !== request) return;
      const rows = page.items.map(run => el('tr', {},
        el('td', {}, el('a', {href: `#/processing/${run.id}`}, run.id.slice(0, 8)), el('div', {className: 'muted'}, `${run.profile_id} · ${run.model}`)),
        el('td', {}, badge(labelStatus(run.status)), run.source_stale && el('small', {className: 'muted'}, ' · 来源已过期')),
        el('td', {}, `v${run.source_version}`), el('td', {}, formatDate(run.created_at))));
      records.replaceChildren(el('div', {className: 'card stack'}, el('div', {className: 'detail-header'}, el('h2', {}, '处理记录'), button('刷新记录', () => loadRuns())),
        rows.length ? dataTable(['运行 / 模型', '状态', '来源版本', '时间'], rows) : empty('还没有处理记录', '选择一条资料和就绪模型，主动生成第一份知识草稿。'), pager(page, loadRuns)));
    } catch (error) {if (!stopped && sequence === request) showError(error, records);}
  }
  async function loadDetail() {
    if (!context.id) return;
    try {
      const run = await api(`/api/v1/processing/runs/${encodeURIComponent(context.id)}`, {signal: controller.signal});
      if (stopped) return;
      detail.replaceChildren(renderRun(run, context, {alive: () => !stopped, onRefresh: loadDetail}));
      detailRunning = run.status === 'running'; return detailRunning;
    } catch (error) {if (!stopped) showError(error, detail); return false;}
  }
  model.addEventListener('change', () => {update(); loadRuns(0);});
  status.addEventListener('change', () => loadRuns(0));
  container.append(...[pageHeading('AI 草稿', '单篇生成、预览与人工采纳。模型调用只在主动点击时执行。'),
    !registry.enabled && notice('AI 当前关闭。可以查看历史草稿；请在本机配置中启用并重启后再生成。'),
    registry.error_code && notice(`模型配置未就绪：${registry.error_code}`, 'warning'),
    el('div', {className: 'card stack'}, el('h2', {}, '生成新草稿'), el('div', {className: 'form-grid'}, picker.node, field('生成模型', model, '配置就绪表示参数和密钥已配置，不代表真实服务已经验证。')),
      sourceInfo, el('div', {className: 'page-actions'}, generation, field('记录状态', status)), errors), detail, records].filter(Boolean));
  await Promise.all([loadSource(selectedId), loadRuns(0), loadDetail()]);
  const stopPoll = pollVisible(async () => {await loadRuns(); if (context.id && detailRunning) await loadDetail();});
  return () => {stopped = true; controller.abort(); picker.close(); stopPoll();};
}
