import {api} from '../api.js';
import {el, button, empty, notice, pageHeading, showError, select} from '../ui.js';
import {numberedPagination} from './numbered-pagination.js';
import {positivePage, pageSize, sourceState, sourceHash, sourceReturn} from './source-navigation.js';
import {sourceCard} from './source-card.js';

export function mountSourceGroup(container, context) {
  const mountedHash = location.hash;
  const title = context.params.get('title');
  const back = sourceReturn(context.params.get('return_to'), '#/sources', false);
  if (title === null) {container.append(notice('缺少资料标题，请从资料库选择标题。', 'warning'), el('a', {href: back}, '返回资料库')); return;}
  const stateValue = sourceState(context.params.get('state')), page = positivePage(context.params.get('page'));
  const size = pageSize(context.params.get('per_page'), [5,10,20], 5);
  const current = sourceHash('group', {title, state: stateValue, page, per_page: size, return_to: back});
  const navigate = values => {if (isCurrent()) context.navigate(sourceHash('group', {title, state: state.value, page, per_page: size, return_to: back, ...values}));};
  const state = select([['active','正常'],['deleted','回收站'],['all','全部']], stateValue); state.setAttribute('aria-label', '组内记录状态');
  state.addEventListener('change', () => navigate({page: 1}));
  const backLink = el('a', {className: 'btn', href: back, 'data-testid': 'source-list-back'}, '← 返回资料库');
  const heading = pageHeading(title, '同标题资料分别保留作者、出处和原文，不合并不同回答。', backLink);
  heading.classList.add('source-group-heading');
  container.append(heading,
    el('div', {className: 'toolbar'}, el('label', {className: 'page-size-field'}, '记录状态', state)));
  const errors = el('div'), summary = el('div'), records = el('div', {className: 'stack'}, el('div', {className: 'loading'}, '正在读取该标题下的资料…')), pagination = el('div');
  container.append(errors, summary, records, pagination);
  const controller = new AbortController(); let disposed = false;
  const isCurrent = () => !disposed && location.hash === mountedHash;
  async function load() {
    try {
      const args = new URLSearchParams({title, state: stateValue, offset: (page-1)*size, limit: size});
      const value = await api(`/api/v1/ui/source-groups/items?${args}`, {signal: controller.signal});
      if (!isCurrent()) return;
      const pages = Math.max(1, Math.ceil(value.total/size));
      if (page > pages) {navigate({page: pages}); return;}
      summary.replaceChildren(el('p', {className: 'muted', 'data-testid': 'source-member-count'}, `此标题共 ${value.total} 篇资料 · 本页 ${value.items.length} 篇`));
      records.replaceChildren();
      const slots = value.items.map(() => el('div', {className: 'card'}, '正在加载原文…'));
      records.append(...slots);
      if (!value.items.length) records.append(empty('该标题下暂无匹配资料', '可以切换记录状态，或返回资料库查看其他标题。'));
      pagination.append(numberedPagination({total: value.total, page, size, sizes: [5,10,20], sizeLabel: '每页资料数', label: '同标题资料分页',
        onPage: target => navigate({page: target}), onSize: target => navigate({page: 1, per_page: target})}));
      let next = 0;
      async function worker() {
        while (isCurrent() && next < value.items.length) {
          const index = next++, item = value.items[index];
          try {
            const record = await api(`/api/v1/sources/${encodeURIComponent(item.id)}?include_deleted=true`, {signal: controller.signal});
            if (isCurrent()) slots[index].replaceWith(sourceCard(record, {index: (page-1)*size + index+1, returnTo: current, title}));
          } catch (error) {if (isCurrent()) {slots[index].replaceChildren(); showError(error, slots[index]);}}
        }
      }
      await Promise.all(Array.from({length: Math.min(3, value.items.length)}, () => worker()));
    } catch (error) {if (isCurrent()) {records.replaceChildren(); showError(error, errors);}}
  }
  load();
  return () => {disposed = true; controller.abort();};
}
