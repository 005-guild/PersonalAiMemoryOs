import {el, button, select} from '../ui.js';

const fields = [['title', '标题'], ['source_count', '资料数量'], ['source_type', '类型'], ['updated_at', '更新时间']];
export function sourceSort(params) {
  const field = params.get('sort_by'), order = params.get('order');
  return {sort_by: fields.some(([key]) => key === field) ? field : 'updated_at', order: ['asc', 'desc'].includes(order) ? order : 'desc'};
}
const defaultOrder = field => ['title', 'source_type'].includes(field) ? 'asc' : 'desc';

export function sourceSortControls(sort, onChange) {
  const field = select(fields, sort.sort_by), order = select([['asc', '升序'], ['desc', '降序']], sort.order);
  field.setAttribute('aria-label', '排序依据'); order.setAttribute('aria-label', '排序方向');
  field.addEventListener('change', () => onChange({sort_by: field.value, order: defaultOrder(field.value)}));
  order.addEventListener('change', () => onChange({sort_by: sort.sort_by, order: order.value}));
  return [el('label', {className: 'source-sort-field'}, '排序依据', field), el('label', {className: 'source-sort-field'}, '排序方向', order)];
}

export function sourceSortHeaders(sort, onChange) {
  return el('tr', {}, ...fields.map(([field, label]) => {
    const active = sort.sort_by === field;
    const order = active ? (sort.order === 'asc' ? 'desc' : 'asc') : defaultOrder(field);
    return el('th', {className: field === 'updated_at' ? 'hide-mobile' : '', 'aria-sort': active ? (sort.order === 'asc' ? 'ascending' : 'descending') : 'none'},
      button(label, () => onChange({sort_by: field, order}), {className: 'source-sort-button', 'aria-label': `按${label}排序`,
        title: `按${label}${order === 'asc' ? '升序' : '降序'}排列`}),
      el('span', {className: 'source-sort-indicator', 'aria-hidden': 'true'}, active ? (sort.order === 'asc' ? '↑' : '↓') : '↕'));
  }));
}
