import {api} from '../api.js';
import {el, button, notice, badge, confirmAction, showError, formatDate} from '../ui.js';
import {labelStatus, dataTable, keyValues} from './workflow-utils.js';

const batchLabels = {pending: '待执行', running: '处理中', paused: '已暂停', completed: '已完成', cancelling: '正在取消', cancelled: '已取消'};
export function batchPanel(id, context, {alive}) {
  const element = el('section', {className: 'card stack', 'data-testid': 'processing-batch-detail'});
  let snapshot, busy = false, request = 0, confirming=false,disposed=false;
  async function settleCurrent(){while(!disposed&&!alive())await new Promise(resolve=>setTimeout(resolve,25));return !disposed&&alive();}
  async function load() {
    const ticket = ++request;
    try {
      const value = await api(`/api/v1/processing/batches/${encodeURIComponent(id)}`);
      if (!alive() || ticket !== request || busy) return;
      snapshot = value; draw();
    } catch (error) {if (alive() && ticket === request) showError(error, element);}
  }
  async function action(kind) {
    if (busy || confirming || !snapshot || !alive()) return;
    const counts = snapshot.counts || {};
    const calls = kind === 'retry-failed' ? (counts.failed || 0) + (counts.interrupted || 0) : counts.pending || 0;
    const message = kind === 'cancel' ? '停止执行后续资料？已完成草稿会保留，在途调用会正常完成并保存。' : `${kind === 'retry-failed' ? '显式重试失败或中断项' : '继续待处理项'}，预计最多发起 ${calls} 次模型调用，可能产生费用。不会重试已完成项。是否继续？`;
    confirming=true;const confirmed=await confirmAction(message, {title: '确认批次操作', confirmLabel: kind === 'cancel' ? '取消后续' : '确认调用'});confirming=false;if(!confirmed||!alive())return;
    busy = true; draw();
    try {const value = await api(`/api/v1/processing/batches/${id}/${kind}`, {method: 'POST', body: {expected_version: snapshot.version}});if(await settleCurrent())snapshot=value;}
    catch (error) {if (await settleCurrent()) showError(error, errors);}
    finally {busy = false; if (alive()) await load();}
  }
  const errors = el('div');
  function draw() {
    const value = snapshot, counts = value.counts || {};
    const active = ['pending', 'running', 'cancelling'].includes(value.status);
    const rows = (value.items || []).map(item => el('tr', {}, el('td', {}, item.position + 1), el('td', {},
      (item.source_ids || []).map(id => value.source_snapshots?.find(source => source.id === id)?.title || id).join('、')),
      el('td', {}, badge(labelStatus(item.status)), item.source_stale && el('small', {}, ' 来源已变化'), item.error_code && el('small', {className: 'status-detail'}, item.error_code)),
      el('td', {}, item.attempts), el('td', {}, item.run_id ? el('a', {href: `#/processing/${item.run_id}`}, '查看草稿 / 运行') : '—',
        item.run_ids?.length>1&&el('details',{},el('summary',{},'历次尝试'),...item.run_ids.map((runId,index)=>el('div',{},el('a',{href:`#/processing/${runId}`},`第 ${index+1} 次运行`)))))));
    element.replaceChildren(el('div', {className: 'detail-header'}, el('h2', {}, '批次进度'), badge(batchLabels[value.status] || value.status)),
      keyValues([['批次 ID', value.id], ['生成方式', value.mode === 'merged' ? '合并为一篇' : '逐篇生成'], ['来源数量', value.source_count],
        ['模型', `${value.profile_id} · ${value.model}`], ['模板',value.prompt_snapshot?`${value.prompt_snapshot.name} · v${value.prompt_snapshot.version}`:'—'],
        ['生成限额',value.generation_settings?`${value.generation_settings.max_output_tokens} tokens · ${value.generation_settings.timeout_seconds} 秒`:'—'],['创建时间', formatDate(value.created_at)]]),
      el('p', {}, `待处理 ${counts.pending || 0} · 处理中 ${counts.running || 0} · 草稿完成 ${counts.ready || 0} · 失败 ${counts.failed || 0} · 中断 ${counts.interrupted || 0} · 取消 ${counts.cancelled || 0}`),
      notice('批次保存在数据库中，离开页面后仍可查找。重启后的遗留任务会暂停；继续与重试必须主动确认，不会自动重复付费调用。'),
      el('div', {className: 'page-actions'},
        button('继续待处理', () => action('continue'), {disabled: busy || active || !counts.pending, 'data-testid': 'batch-continue'}),
        button('重试失败 / 中断项', () => action('retry-failed'), {disabled: busy || active || !(counts.failed || counts.interrupted), 'data-testid': 'batch-retry'}),
        button('取消后续', () => action('cancel'), {disabled: busy || !['pending','running','paused'].includes(value.status), 'data-testid': 'batch-cancel'}), button('刷新进度', load, {disabled: busy})),
      errors, dataTable(['序号', '来源', '状态', '调用次数', '结果'], rows));
  }
  load(); return {element, refresh: load,dispose:()=>{disposed=true;request++;}};
}
