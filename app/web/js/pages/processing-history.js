import {api} from '../api.js';
import {el, button, field, empty, badge, formatDate, showError} from '../ui.js';
import {select, pager, dataTable, labelStatus, profilePicker} from './workflow-utils.js';
import {listState} from './list-pagination.js';

/** History filters deliberately do not share controls or state with generation. */
export function processingHistory(registry, context, {alive, signal}) {
  const stored = listState('processing-runs', {status:'', source:'', profile:''}), state = stored.value;
  const batchStored = listState('processing-batches'), batchState = batchStored.value;
  const status = select([['', '全部状态'], ...['running','ready','adopted','failed','interrupted'].map(value => [value, labelStatus(value)])]);
  status.setAttribute('aria-label', '处理记录状态');
  const source = el('input', {placeholder: '来源 UUID（可选）', 'aria-label': '历史来源 UUID'});
  const profile = profilePicker(registry, {emptyLabel: '全部模型配置'}); profile.setAttribute('aria-label', '历史模型配置');
  profile.options[0].textContent='全部模型配置';
  const records = el('div'), batches = el('div'), errors = el('div');
  const element = el('section', {className: 'card stack'}, el('div', {className: 'detail-header'}, el('h2', {}, '处理历史'), button('刷新记录', () => refresh())),
    el('div', {className: 'form-grid'}, field('历史来源', source), field('历史模型', profile), field('记录状态', status)),
    el('a', {href: '#/drafts'}, '打开草稿箱 →'), errors, records,
    el('h3', {}, '持久批次'), batches);
  let offset = state.offset, size = state.size, sequence = 0, batchOffset=batchState.offset, batchSize=batchState.size, batchSequence=0;
  status.value=state.status;source.value=state.source;profile.value=state.profile;
  async function loadRuns(next = offset, nextSize = size) {
    offset = next; size = nextSize;Object.assign(state,{offset,size,status:status.value,source:source.value,profile:profile.value});stored.save(); const ticket = ++sequence;
    const query = new URLSearchParams({offset, limit: size, summary_only: 'true'});
    if (source.value.trim()) query.set('source_id', source.value.trim());
    if (status.value) query.set('status', status.value); if (profile.value) query.set('profile_id', profile.value);
    try {
      const page = await api(`/api/v1/processing/runs?${query}`, {signal}); if (!alive() || ticket !== sequence) return;
      if(offset&&offset>=page.total)return loadRuns(Math.max(0,Math.floor((page.total-1)/size)*size));
      records.replaceChildren(page.items.length ? dataTable(['运行 / 模型', '状态', '来源数', '时间'], page.items.map(run => el('tr', {},
        el('td', {}, el('a', {href: `#/drafts/${run.id}`}, run.title || run.result?.title || run.id.slice(0,8)), el('small', {className: 'status-detail'}, `${run.profile_id} · ${run.model}`)),
        el('td', {}, badge(labelStatus(run.status)), run.source_stale && ' · 来源已变化'),
        el('td', {}, run.source_count || run.source_snapshots?.length || 1), el('td', {}, formatDate(run.created_at))))) : empty('还没有处理记录'), pager(page, loadRuns));
    } catch (error) {if (alive() && ticket === sequence) showError(error, errors);}
  }
  async function loadBatches(next=batchOffset,nextSize=batchSize) {
    batchOffset=next;batchSize=nextSize;Object.assign(batchState,{offset:batchOffset,size:batchSize});batchStored.save();const ticket=++batchSequence;
    try {const page = await api(`/api/v1/processing/batches?offset=${batchOffset}&limit=${batchSize}`, {signal}); if (!alive()||ticket!==batchSequence) return;
      batches.replaceChildren(page.items.length ? dataTable(['批次', '方式 / 来源', '状态', '时间'], page.items.map(item => el('tr', {},
        el('td', {}, el('a', {href: `#/processing?batch_id=${item.id}`}, item.id.slice(0,8))), el('td', {}, `${item.mode === 'merged' ? '合并' : '逐篇'} · ${item.source_count} 篇`), el('td', {}, ({pending:'待执行',running:'处理中',paused:'已暂停',completed:'已完成',cancelling:'正在取消',cancelled:'已取消'})[item.status]||item.status), el('td', {}, formatDate(item.created_at))))) : empty('还没有批次'),pager(page,loadBatches));
    } catch (error) {if (alive()&&ticket===batchSequence) showError(error, batches);}
  }
  async function refresh() {await Promise.all([loadRuns(), loadBatches()]);}
  for (const input of [status, source, profile]) input.addEventListener('change', () => loadRuns(0));
  refresh(); return {element, refresh, statusField:field('历史记录状态',status)};
}
