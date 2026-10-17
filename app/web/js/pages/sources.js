import {api} from '../api.js';
import {el, button, badge, empty, formatDate, showError, pageHeading, select, debounce} from '../ui.js';
import {numberedPagination} from './numbered-pagination.js';
import {positivePage, pageSize, sourceState, sourceHash} from './source-navigation.js';
import {sourceSort, sourceSortControls, sourceSortHeaders} from './source-sorting.js';

let pendingControlFocus = null;

export function mountSources(container, context) {
  const mountedHash = location.hash;
  const query = context.params.get('q') || '', stateValue = sourceState(context.params.get('state'));
  const page = positivePage(context.params.get('page')), size = pageSize(context.params.get('per_page'), [10,20,50,100], 20);
  const sort = sourceSort(context.params);
  const current = sourceHash('', {q: query, state: stateValue, page, per_page: size, ...sort});
  const navigate = (values, preserveControl = null) => {
    if (!isCurrent()) return;
    const hash = sourceHash('', {q: search.value, state: state.value, page, per_page: size, ...sort, ...values});
    if (hash === location.hash) return;
    const control = preserveControl ? container.querySelector(`[aria-label="${preserveControl}"]`) : null;
    pendingControlFocus = control && document.activeElement === control ? {hash, label: preserveControl, start: control.selectionStart, end: control.selectionEnd} : null;
    context.navigate(hash);
  };
  container.append(pageHeading('资料库', '相同标题合并显示，打开后阅读该标题下的每篇原始资料。',
    button('＋ 新建资料', () => context.navigate(`#/sources/new?${new URLSearchParams({return_to: current})}`), {className: 'btn btn-primary'})));
  const search = el('input', {type: 'search', value: query, placeholder: '按标题搜索…', 'aria-label': '标题筛选'});
  const state = select([['active','正常'],['deleted','回收站'],['all','全部']], stateValue); state.setAttribute('aria-label','记录状态');
  const changeSort = values => {
    delayed.cancel();
    const label = document.activeElement?.getAttribute('aria-label');
    navigate({page: 1, ...values}, ['排序依据', '排序方向'].includes(label) ? label : null);
  };
  const errorBox = el('div'), results = el('div', {}, el('div', {className: 'loading'}, '正在读取资料标题…'));
  container.append(el('section', {className: 'card'}, el('div', {className: 'toolbar source-list-toolbar'}, search, state, ...sourceSortControls(sort, changeSort)), errorBox, results));
  const controller = new AbortController(); let disposed = false, composing = false, focusFrame;
  const isCurrent = () => !disposed && location.hash === mountedHash;
  const delayed = debounce(() => navigate({page: 1}, '标题筛选'));
  search.addEventListener('compositionstart', () => {composing = true; delayed.cancel();});
  search.addEventListener('compositionend', () => {composing = false; delayed();});
  search.addEventListener('input', () => {if (!composing) delayed();});
  state.addEventListener('change', () => {delayed.cancel(); navigate({page: 1});});
  async function load() {
    try {
      const args = new URLSearchParams({q: query, state: stateValue, offset: (page-1)*size, limit: size, ...sort});
      const value = await api(`/api/v1/ui/source-groups?${args}`, {signal: controller.signal});
      if (!isCurrent()) return;
      const pages = Math.max(1, Math.ceil(value.total/size));
      if (page > pages) {navigate({page: pages}); return;}
      results.replaceChildren(el('p', {className: 'muted', 'data-testid': 'source-group-count'}, `共 ${value.total} 个标题 · ${value.total_sources} 篇资料`));
      if (!value.items.length) results.append(empty('没有匹配的资料标题', query ? '换一个关键词或记录状态。' : '新建资料或从离线导入开始。'));
      else results.append(el('div', {className: 'table-wrap'}, el('table', {className: 'data-table'},
        el('thead', {}, sourceSortHeaders(sort, changeSort)),
        el('tbody', {}, ...value.items.map(item => el('tr', {},
          el('td', {}, el('a', {className: 'record-title', 'data-testid': 'source-group-link',
            href: sourceHash('group', {title: item.title, state: stateValue, page: 1, per_page: 20, return_to: current})}, item.title)),
          el('td', {}, badge(`${item.source_count} 篇`, 'info'), el('small', {className: 'status-detail'}, `正常 ${item.active_count} · 已删除 ${item.deleted_count}`)),
          el('td', {}, (item.source_types || []).join('、')), el('td', {className: 'hide-mobile'}, formatDate(item.latest_updated_at))))))));
      results.append(numberedPagination({total: value.total, page, size, sizes: [10,20,50,100], sizeLabel: '每页标题数', label: '资料标题分页',
        onPage: target => navigate({page: target}), onSize: target => navigate({page: 1, per_page: target})}));
    } catch (error) {if (isCurrent()) {results.replaceChildren(); showError(error, errorBox);}}
  }
  load();
  const focus = pendingControlFocus; pendingControlFocus = null;
  if (focus?.hash === location.hash) focusFrame = requestAnimationFrame(() => {
    if (isCurrent()) {
      const control = container.querySelector(`[aria-label="${focus.label}"]`);
      control?.focus({preventScroll: true});
      if (control === search) search.setSelectionRange(focus.start, focus.end);
    }
  });
  return () => {disposed = true; controller.abort(); delayed.cancel(); if (focusFrame) cancelAnimationFrame(focusFrame);};
}
