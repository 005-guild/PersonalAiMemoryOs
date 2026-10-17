import {api} from '../api.js';
import {el, button, field, notice, empty, formatDate, showError} from '../ui.js';

export const statusLabels = {running: '生成中', ready: '待采纳', failed: '失败', interrupted: '已中断', adopted: '已采纳', open: '待解决', resolved: '已解决', superseded: '已有新冲突', created: '已创建', skipped: '已跳过', invalid: '无效', would_create: '预计创建'};
export const labelStatus = value => statusLabels[value] || value || '—';
export const select = (entries, value = '') => el('select', {}, ...entries.map(([id, label]) => el('option', {value: id, selected: id === value}, label)));
export const jsonView = value => el('pre', {className: 'mono snapshot'}, JSON.stringify(value, null, 2));
export const details = (title, ...content) => el('details', {}, el('summary', {}, title), ...content);
export const keyValues = entries => el('dl', {className: 'key-values'}, ...entries.flatMap(([key, value]) => [el('dt', {}, key), el('dd', {}, value ?? '—')]));
export function dataTable(headers, rows) {
  return el('div', {className: 'table-wrap'}, el('table', {className: 'data-table'},
    el('thead', {}, el('tr', {}, ...headers.map(title => el('th', {}, title)))), el('tbody', {}, ...rows)));
}

export function pager(page, load) {
  return el('div', {className: 'pagination'},
    el('span', {className: 'muted'}, `共 ${page.total} 条 · 第 ${Math.floor(page.offset / page.limit) + 1} 页`),
    button('上一页', () => load(Math.max(0, page.offset - page.limit)), {disabled: page.offset === 0}),
    button('下一页', () => load(page.offset + page.limit), {disabled: page.offset + page.limit >= page.total}));
}

// Poll only while the page is visible. Never poll a form or replay a mutation.
export function pollVisible(refresh, interval = 5000) {
  let stopped = false, running = false;
  const tick = async () => {
    if (stopped || document.hidden || running) return;
    running = true;
    try {await refresh();}
    catch (error) {if (!stopped) showError(error);}
    finally {running = false;}
  };
  const timer = setInterval(tick, interval);
  document.addEventListener('visibilitychange', tick);
  return () => {stopped = true; clearInterval(timer); document.removeEventListener('visibilitychange', tick);};
}

/** Paged source lookup keeps two-million-character source bodies out of selectors. */
export function sourcePicker(onChange, {selected = '', includeAll = true, signal} = {}) {
  let offset = 0, request = 0, timer, stopped = false;
  const input = el('input', {type: 'search', placeholder: '输入资料标题筛选', 'aria-label': '筛选来源标题'});
  const choices = select([[selected, selected ? '正在读取所选来源…' : includeAll ? '全部来源' : '请选择来源']], selected);
  choices.setAttribute('aria-label', '来源资料');
  const feedback = el('div');
  const paging = el('div');
  let currentId = selected;
  choices.addEventListener('change', () => {currentId = choices.value; onChange(currentId);});
  async function load(nextOffset = 0) {
    offset = nextOffset; const sequence = ++request;
    try {
      const query = new URLSearchParams({state: 'active', q: input.value, offset: String(offset), limit: '20'});
      const page = await api(`/api/v1/ui/sources?${query}`, {signal});
      if (stopped || sequence !== request) return;
      const options = [['', includeAll ? '全部来源' : '请选择来源'], ...page.items.map(item => [item.id, item.title])];
      if (currentId && !page.items.some(item => item.id === currentId)) {
        const source = await api(`/api/v1/sources/${encodeURIComponent(currentId)}`, {signal});
        if (stopped || sequence !== request) return;
        options.splice(1, 0, [source.id, `${source.title}${source.deleted_at ? '（已删除）' : ''}`]);
      }
      choices.replaceChildren(...options.map(([id, label]) => el('option', {value: id, selected: id === currentId}, label)));
      feedback.replaceChildren(); paging.replaceChildren(pager(page, load));
    } catch (error) {if (!stopped && sequence === request) showError(error, feedback);}
  }
  input.addEventListener('input', () => {clearTimeout(timer); timer = setTimeout(() => load(), 280);});
  load();
  return {node: el('div', {className: 'stack source-picker'}, field('查找来源', input), choices, paging, feedback),
    get value() {return currentId;}, close() {stopped = true; request++; clearTimeout(timer);}};
}

export function profilePicker(registry, {emptyLabel = '使用默认配置'} = {}) {
  const picker = select([['', `${emptyLabel}${registry.default_profile ? `（${registry.default_profile}）` : ''}`],
    ...(registry.items || []).map(item => [item.id, `${item.label || item.id} · ${item.model}${!item.enabled ? ' · 已禁用' : !item.configured ? ' · 未就绪' : ''}`])]);
  picker.setAttribute('aria-label', '模型配置');
  return picker;
}

export function profileReady(registry, selected) {
  const profile = registry.items?.find(item => item.id === (selected || registry.default_profile));
  return Boolean(registry.enabled && !registry.error_code && profile?.enabled && profile?.configured);
}

export function profilesTable(registry) {
  if (!registry.items?.length) return empty('没有可用配置', registry.error_code || '请在本机配置文件中添加模型配置，重启服务后生效。');
  return el('div', {className: 'table-wrap'}, el('table', {className: 'data-table'},
    el('thead', {}, el('tr', {}, ...['配置', '协议 / 模型', '状态'].map(value => el('th', {}, value)))),
    el('tbody', {}, ...registry.items.map(item => el('tr', {},
      el('td', {}, item.label || item.id, item.id === registry.default_profile && el('small', {className: 'muted'}, ' · 默认')),
      el('td', {}, el('div', {}, item.model), el('small', {className: 'muted'}, item.protocol), item.dimension && el('small', {className: 'muted'}, ` · ${item.dimension} 维`)),
      el('td', {}, !item.enabled ? '配置已禁用' : item.configured ? '配置就绪' : '缺少密钥'))))));
}

export {formatDate};
