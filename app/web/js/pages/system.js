import {api} from '../api.js';
import {el, button, notice, badge, empty, pageHeading, formatDate, confirmAction, showError} from '../ui.js';
import {pollVisible, profilesTable, jsonView, details, keyValues} from './workflow-utils.js';
import {conflictsPanel} from './system-conflicts.js';
import {entryGrid,backLink} from './workspace-common.js';
import {remoteList} from './remote-list.js';

function counts(value = {}) {return el('div', {className: 'page-actions'}, ...Object.entries(value).map(([name, count]) => badge(`${({published: '已发布', pending: '待处理', failed: '失败', excluded: '已排除', synced: '已同步', conflict: '冲突', error: '错误', deleted: '已删除'})[name] || name} ${count}`)));}

function syncDetails(status) {
  const problems = (status.notes || []).filter(note => note.last_error || !['synced', 'deleted'].includes(note.status));
  return el('div', {className: 'stack'},
    keyValues([['自动同步', status.enabled ? '已开启' : '已关闭'], ['后台任务', status.running ? '运行中' : '已停止'], ['上次扫描', formatDate(status.last_scan_at)]]),
    counts(status.counts), status.last_error && notice(status.last_error, 'error'),
    el('p', {className: 'muted'}, `文件问题 ${status.issue_count || 0} 条；笔记同步记录 ${status.note_count || 0} 条。请在下方分页明细中查看。`),
    problems.length > 0 && details(`待处理 / 异常笔记（${problems.length}）`,
      el('div', {className: 'table-wrap'}, el('table', {className: 'data-table'}, el('tbody', {}, ...problems.map(note => el('tr', {},
        el('td', {}, el('a', {href: `#/knowledge/${note.knowledge_id}`}, note.path || note.knowledge_id)), el('td', {}, note.status), el('td', {}, note.last_error || '等待同步'))))))),
    !status.last_error && !status.issue_count && !status.counts?.error && !status.counts?.pending && !problems.length && el('p', {className: 'muted'}, '当前没有待处理的文件问题。'));
}

function indexDetails(status) {
  return el('div', {className: 'stack'},
    keyValues([['RAG', status.enabled ? '已开启' : '已关闭'], ['后台对账', status.worker_running ? '运行中' : '已停止'], ['当前任务', status.running ? '执行中' : '空闲'], ['上次对账', formatDate(status.last_scan_at)]]),
    counts(status.counts), status.last_error && notice(status.last_error, 'error'),
    status.enabled && status.index_incomplete && notice('索引尚未完整；检索只使用已发布且仍有效的笔记片段。', 'warning'),
    status.generation ? details('当前索引代次', jsonView(status.generation)) : el('p', {className: 'muted'}, '尚无索引代次。'),
    el('p', {className: 'muted'}, `索引错误 ${status.error_count || 0} 条；排除 ${status.counts?.excluded || 0} 篇。明细独立分页。`));
}

export function mount(container,context){
  const mode=context.id;
  container.append(backLink('#/settings','设置'),pageHeading('系统维护','文件同步、冲突与知识索引分别维护。'));
  if(!mode){container.append(entryGrid([['文件同步','状态、扫描与同步记录','#/system/sync'],['同步冲突','逐项对照并选择版本','#/system/conflicts'],['知识索引','更新索引与查看异常','#/system/index']]));return;}
  let disposed=false,busy=false;const controller=new AbortController(),alive=()=>!disposed;
  const body=el('section',{className:'card stack'}),errors=el('div');container.append(body,errors);
  if(mode==='conflicts'){const panel=conflictsPanel(context,{alive,signal:controller.signal});body.append(panel.node);return()=>{disposed=true;controller.abort();};}
  const detailEndpoints={'sync-issues':['/api/v1/sync/issues','文件问题'],'sync-notes':['/api/v1/sync/notes','笔记同步明细'],'index-errors':['/api/v1/rag/index/errors','索引错误'],'index-excluded':['/api/v1/rag/index/excluded','索引排除']};
  if(detailEndpoints[mode]){
    const [endpoint,label]=detailEndpoints[mode];body.append(remoteList(endpoint,rows=>el('div',{},...rows.map(row=>el('article',{className:'result-card'},row.knowledge_id&&el('a',{href:'#/knowledge/'+row.knowledge_id},row.title||row.path||row.knowledge_id),jsonView(row)))),{label,alive,signal:controller.signal}).element);
    return()=>{disposed=true;controller.abort();};
  }
  if(!['sync','index'].includes(mode)){body.append(notice('没有此维护页面。'));return;}
  const status=el('div'),actions=el('div',{className:'page-actions'});body.append(el('h2',{},mode==='sync'?'文件同步':'知识索引'),actions,status);
  let state;
  async function run(action){
    if(busy||!alive())return;
    if(mode==='index'&&!await confirmAction(action==='rebuild'?'重建期间检索可能不可用，新的向量调用可能计费。是否继续？':action==='retry'?'显式重试可能再次产生向量费用。是否继续？':'更新索引可能调用向量服务。是否继续？',{confirmLabel:'继续执行'}))return;
    busy=true;update();
    try{await api(mode==='sync'?'/api/v1/sync/run':'/api/v1/rag/index/'+(action==='rebuild'?'rebuild':'run'),{method:'POST',...(mode==='sync'||action==='rebuild'?{}:{body:{retry_failed:action==='retry'}})});if(alive())await refresh();}
    catch(error){if(alive())showError(error,errors);}finally{busy=false;update();}
  }
  for(const [action,label] of mode==='sync'?[['run','立即同步一轮']]:[['run','更新索引'],['retry','重试失败项']])actions.append(button(label,()=>run(action)));
  if(mode==='index'){const advanced=el('details',{},el('summary',{},'高级维护'),button('重建索引',()=>run('rebuild')));body.append(advanced);}
  body.append(...(mode==='sync'?[['sync-issues','文件问题'],['sync-notes','同步明细']]:[['index-errors','索引错误'],['index-excluded','排除记录']]).map(([id,label])=>el('a',{href:'#/system/'+id},label+' →')));
  function update(){for(const button of body.querySelectorAll('button'))button.disabled=busy||(mode==='index'&&(!state?.enabled||state.running));}
  async function refresh(){try{const value=await api(mode==='sync'?'/api/v1/sync/status?summary_only=true':'/api/v1/rag/index/status?summary_only=true',{signal:controller.signal});if(alive()){state=value;status.replaceChildren(mode==='sync'?syncDetails(value):indexDetails(value));update();}}catch(error){if(alive()&&error.name!=='AbortError')showError(error,errors);}}
  refresh();const stop=pollVisible(refresh);return()=>{disposed=true;controller.abort();stop();};
}
