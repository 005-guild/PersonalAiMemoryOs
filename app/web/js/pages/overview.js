import {api} from '../api.js';
import {el, badge, empty, notice, formatDate, pageHeading} from '../ui.js';

const link = (label, href, primary = false) => el('a', {href, className: `btn ${primary ? 'btn-primary' : ''}`}, label);
export async function mount(container) {
  container.append(pageHeading('让知识，持续生长', '欢迎回到你的个人知识工作空间。'));
  const stats = el('div', {className: 'stat-grid'});
  const values = [['原始资料','▤','active_sources','收集与保留原始信息'],['知识笔记','▧','active_knowledge','沉淀经过思考的知识'],['待采纳草稿','✧','ready_drafts','等待你的审阅与确认'],['同步冲突','⇄','open_conflicts','需要手动选择的版本']];
  for (const [label,icon,,hint] of values) stats.append(el('div', {className:'card stat-card'},
    el('div',{className:'stat-label'},label),el('span',{className:'stat-icon','aria-hidden':true},icon),
    el('div',{className:'stat-value'},'—'),el('div',{className:'stat-hint'},hint)));
  container.append(stats);
  container.append(el('section',{className:'card hero'},el('div',{},el('h2',{},'从一条信息，到属于你的洞察'),
    el('p',{},'收藏值得留存的资料，整理自己的笔记。需要时，让知识库为你的思考提供依据。'),
    el('div',{className:'page-actions'},link('＋ 新建笔记','#/knowledge/new',true),link('导入资料 ↗','#/imports'))),
    el('div',{className:'hero-decoration','aria-hidden':true},'▱')));
  const activity = el('section',{className:'card'});
  const status = el('section',{className:'card'});
  container.append(el('div',{className:'grid'},el('div',{},activity,el('section',{className:'card'},
    el('div',{className:'section-header'},el('h2',{},'开始整理')),el('div',{className:'quick-grid'},
      ...[['↥','导入资料','从 JSON 文件开始','#/imports'],['✧','生成草稿','让 AI 帮你整理','#/processing'],['⌕','搜索问答','找回已有的知识','#/search']].map(([icon,title,desc,href]) =>
        el('a',{className:'quick-link',href},el('span',{className:'quick-icon'},icon),el('strong',{},title),el('small',{},desc)))))),
    el('div',{},status,el('section',{className:'card'},el('h2',{},'你的知识，始终在本地'),
      el('p',{className:'muted'},'笔记以 Markdown 保存，资料和处理记录保存在本地数据库。你可以在这里编辑，也可以使用自己熟悉的编辑器。'),
      el('a',{href:'#/system'},'查看同步与配置状态 →')))));
  let disposed = false;
  async function refresh() {
    if (document.hidden || disposed) return;
    const results = await Promise.allSettled([api('/api/v1/ui/overview'),api('/api/v1/ui/knowledge?limit=5'),api('/api/v1/sync/status'),api('/api/v1/ai/profiles'),api('/api/v1/rag/index/status')]);
    if (disposed) return;
    if (results[0].status === 'fulfilled') stats.querySelectorAll('.stat-value').forEach((node,i) => node.textContent = results[0].value[values[i][2]]);
    activity.replaceChildren(el('div',{className:'section-header'},el('h2',{},'最近更新'),el('a',{href:'#/knowledge'},'全部笔记 →')));
    if (results[1].status === 'fulfilled' && results[1].value.items.length) {
      for (const item of results[1].value.items) activity.append(el('div',{className:'status-row'},
        el('div',{},el('a',{href:`#/knowledge/${item.id}`},item.title),el('span',{className:'status-detail'},formatDate(item.updated_at))), badge(item.category || '未分类')));
    } else activity.append(empty('第一篇笔记，从这里开始','记录一次阅读、一个想法，或从资料生成草稿。',link('创建第一篇笔记','#/knowledge/new')));
    status.replaceChildren(el('div',{className:'section-header'},el('h2',{},'工作空间状态'),el('a',{href:'#/system'},'查看详情 →')));
    const sync = results[2].value, ai = results[3].value, rag = results[4].value;
    for (const [title,detail,label,tone] of [
      ['Markdown 同步',sync?.last_error || (sync?.enabled ? '笔记与本地文件保持同步' : '自动同步已关闭'),sync?.last_error ? '异常' : sync?.running ? '运行中' : '未运行',sync?.last_error?'error':sync?.running?'success':''],
      ['AI 文本生成',ai?.error_code || '使用已配置的模型生成知识草稿',ai?.enabled?'已启用':'已关闭',ai?.enabled?'success':''],
      ['语义检索',rag?.last_error || '增量索引与带引用的知识问答',rag?.enabled?'已启用':'已关闭',rag?.enabled?'success':''],
    ]) status.append(el('div',{className:'status-row'},el('div',{},el('strong',{},title),el('span',{className:'status-detail'},detail)),badge(label,tone)));
    if (results.some(item => item.status === 'rejected')) status.append(notice('部分状态暂时无法读取，可前往系统页面检查。','warning'));
  }
  await refresh(); const timer = setInterval(refresh,5000); return () => {disposed=true;clearInterval(timer);};
}
