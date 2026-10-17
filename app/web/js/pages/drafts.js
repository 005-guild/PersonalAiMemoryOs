import {api} from '../api.js';
import {el, button, field, empty, badge, formatDate, showError, pageHeading, select, debounce} from '../ui.js';
import {dataTable, pager, labelStatus, pollVisible} from './workflow-utils.js';
import {renderRun} from './processing-detail.js';
import {listState} from './list-pagination.js';

export function mount(container, context) {
  const mountedHash = location.hash, controller = new AbortController(); let disposed = false, sequence = 0;
  const alive = () => !disposed && location.hash === mountedHash;
  const errors = el('div'), body = el('div');
  container.append(pageHeading(context.id ? '草稿详情' : '草稿箱', '生成结果先在这里审阅，采纳后才成为知识笔记。',
    el('a', {className: 'btn', href: context.id ? '#/drafts' : '#/processing'}, context.id ? '← 返回草稿箱' : '前往 AI 分析')), errors, body);
  if (context.id) {
    async function load() {const ticket = ++sequence;
      try {const run = await api(`/api/v1/processing/runs/${encodeURIComponent(context.id)}`, {signal: controller.signal});
        if (alive() && ticket === sequence) body.replaceChildren(renderRun(run, context, {alive, onRefresh: load}));
      } catch (error) {if (alive() && ticket === sequence) showError(error, errors);}}
    load(); return () => {disposed = true; controller.abort();};
  }
  const saved = listState('drafts', {q: '', state: 'ready', source_id: '', profile_id: ''}), state = saved.value;
  const search = el('input', {type: 'search', value: state.q, placeholder: '按草稿标题搜索…', 'aria-label': '搜索草稿标题'});
  const status = select([['ready','待采纳'],['adopted','已采纳'],['all','全部草稿']], state.state); status.setAttribute('aria-label', '草稿状态');
  const source = el('input', {value: state.source_id, placeholder: '来源 UUID（可选）', 'aria-label': '草稿来源 UUID'});
  const profile = el('input', {value: state.profile_id, placeholder: '模型配置 ID（可选）', 'aria-label': '草稿模型配置'});
  container.insertBefore(el('section', {className: 'card stack'}, el('div', {className: 'toolbar'}, search, field('草稿状态', status), source, profile, button('刷新草稿', () => load()))), errors);
  async function load(offset = state.offset, size = state.size) {
    Object.assign(state, {offset, size, q: search.value, state: status.value, source_id: source.value.trim(), profile_id: profile.value.trim()}); saved.save(); const ticket = ++sequence;
    try {const params = new URLSearchParams({q: state.q, state: state.state, offset, limit: size});
      if (state.source_id) params.set('source_id', state.source_id); if (state.profile_id) params.set('profile_id', state.profile_id);
      const page = await api(`/api/v1/ui/drafts?${params}`, {signal: controller.signal}); if (!alive() || ticket !== sequence) return;
      if (offset && offset >= page.total) return load(Math.max(0, Math.floor((page.total-1)/size)*size));
      body.replaceChildren(el('section', {className: 'card'}, page.items.length ? dataTable(['草稿', '模型 / 模板', '状态 / 来源', '生成时间'], page.items.map(item => el('tr', {},
        el('td', {}, el('a', {href: `#/drafts/${item.id}`, className: 'record-title'}, item.title || item.id.slice(0,8)), el('small', {className: 'record-excerpt'}, item.excerpt || '')),
        el('td', {}, `${item.profile_id} · ${item.model}`, el('small', {className: 'status-detail'}, item.prompt_template_name ? `${item.prompt_template_name} · v${item.prompt_template_version}` : '旧版模板')),
        el('td', {}, badge(labelStatus(item.status)), el('small', {className: 'status-detail'}, `${item.source_count} 篇来源`)), el('td', {}, formatDate(item.created_at))))) : empty('还没有匹配草稿', '到 AI 分析选择资料主动生成；失败和中断记录在任务历史查看。'), pager(page, load, '草稿箱分页')));
    } catch (error) {if (alive() && ticket === sequence) showError(error, errors);}
  }
  const delayed = debounce(() => load(0)); search.addEventListener('input', delayed);
  for (const node of [status,source,profile]) node.addEventListener('change', () => load(0));
  load(); const stop = pollVisible(() => load());
  return () => {disposed = true; controller.abort(); delayed.cancel(); stop();};
}
