import {api} from '../api.js';
import {el, button, notice, badge, confirmAction, showError, formatDate} from '../ui.js';
import {labelStatus, dataTable, keyValues} from './workflow-utils.js';
import {remoteList} from './remote-list.js';

export function batchPanel(id, context, {alive}) {
  const element = el('section', {className: 'card stack', 'data-testid': 'processing-batch-detail'}), metadata = el('div'), errors = el('div');
  let snapshot, busy = false, request = 0, confirming = false, disposed = false;
  const active = () => !disposed && alive();
  const items = remoteList(`/api/v1/processing/batches/${id}/items`, rows => dataTable(['序号','来源','状态','调用次数','结果'], rows.map(item => {
    const attempts = el('details', {}, el('summary', {}, '历次尝试')); let loaded = false;
    attempts.addEventListener('toggle', () => {if (!attempts.open || loaded) return; loaded = true;
      const panel = remoteList(`/api/v1/processing/batches/${id}/items/${item.id}/attempts`, runs => dataTable(['运行','状态','时间'], runs.map(run => el('tr', {},
        el('td', {}, el('a', {href: `#/drafts/${run.id}`}, run.id.slice(0,8))), el('td', {}, labelStatus(run.status)), el('td', {}, formatDate(run.created_at))))),
        {label:'任务尝试分页',key:`attempts:${item.id}`,alive:()=>active()&&attempts.isConnected});attempts.append(panel.element);
    });
    return el('tr', {}, el('td', {}, item.position+1), el('td', {}, (item.sources || []).map(source=>source.title).join('、') || (item.source_ids || []).join('、')),
      el('td', {}, badge(labelStatus(item.status)),item.source_stale&&' · 来源已变化',item.error_code&&el('small', {className:'status-detail'},item.error_code)),
      el('td', {}, item.attempts),el('td', {},item.run_id?el('a',{href:`#/drafts/${item.run_id}`},'查看草稿 / 运行'):'—',item.attempts>0&&attempts));
  })), {label:'批次任务分页',key:`batch-items:${id}`,alive:active});
  async function load() {
    const ticket = ++request;
    try {const value = await api(`/api/v1/processing/batches/${encodeURIComponent(id)}?summary_only=true`);
      if (active() && ticket === request && !busy) {snapshot = value; draw();}
    } catch (error) {if (active() && ticket === request) showError(error, errors);}
  }
  async function action(kind) {
    if (busy || confirming || !snapshot || !active()) return;
    const counts=snapshot.counts||{},calls=kind==='retry-failed'?(counts.failed||0)+(counts.interrupted||0):counts.pending||0;
    confirming=true;const confirmed=await confirmAction(kind==='cancel'?'停止后续资料？已完成草稿保留，当前调用正常收尾。':`${kind==='retry-failed'?'重试失败／中断项':'继续待处理项'}预计最多 ${calls} 次模型调用，可能收费。不会重试已完成项。是否继续？`,{title:'确认批次操作',confirmLabel:kind==='cancel'?'取消后续':'确认调用'});
    confirming=false;if(!confirmed||!active())return;busy=true;draw();
    try {await api(`/api/v1/processing/batches/${id}/${kind}`,{method:'POST',body:{expected_version:snapshot.version}});}
    catch(error){if(active())showError(error,errors);}
    finally{busy=false;if(active()){await load();await items.refresh();}}
  }
  function draw() {
    const value=snapshot,counts=value.counts||{},running=['pending','running','cancelling'].includes(value.status);
    metadata.replaceChildren(el('div',{className:'detail-header'},el('h2',{},'批次进度'),badge(labelStatus(value.status))),
      keyValues([['批次 ID',value.id],['生成方式',value.mode==='merged'?'合并分析':'逐篇生成'],['来源数量',value.source_count],['模型',`${value.profile_id} · ${value.model}`],['创建时间',formatDate(value.created_at)]]),
      el('p',{},`待处理 ${counts.pending||0} · 处理中 ${counts.running||0} · 草稿完成 ${counts.ready||0} · 失败 ${counts.failed||0} · 中断 ${counts.interrupted||0} · 取消 ${counts.cancelled||0}`),
      notice('批次持久保存；重启暂停剩余项，不会自动重复付费调用。任务列表独立分页，点击刷新列表查看最新逐项结果。'),
      el('div',{className:'page-actions'},button('继续待处理',()=>action('continue'),{disabled:busy||running||!counts.pending,'data-testid':'batch-continue'}),
        button('重试失败 / 中断项',()=>action('retry-failed'),{disabled:busy||running||!(counts.failed||counts.interrupted),'data-testid':'batch-retry'}),
        button('取消后续',()=>action('cancel'),{disabled:busy||!['pending','running','paused'].includes(value.status),'data-testid':'batch-cancel'}),button('刷新进度',async()=>{await load();await items.refresh();},{disabled:busy})));
  }
  element.append(metadata,errors,items.element);load();return{element,refresh:load,dispose(){disposed=true;request++;}};
}
