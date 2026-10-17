import {el, button, notice, select} from '../ui.js';

export function numberedPagination({total, page, size, sizes, sizeLabel, label, onPage, onSize}) {
  const pages = Math.max(1, Math.ceil(total / size)), errors = el('div');
  const jump = el('input', {type: 'text', inputMode: 'numeric', value: String(page), 'aria-label': '跳转页码', className: 'page-jump-input'});
  const sizeSelect = select(sizes.map(value => [String(value), `${value} 条 / 页`]), String(size));
  sizeSelect.setAttribute('aria-label', sizeLabel); sizeSelect.addEventListener('change', () => onSize(Number(sizeSelect.value)));
  function go() {
    const value = jump.value.trim(), target = Number(value);
    if (!/^[1-9]\d*$/.test(value) || !Number.isSafeInteger(target) || target > pages) {
      errors.replaceChildren(notice(`请输入 1 至 ${pages} 之间的整数页码。`, 'warning')); return;
    }
    errors.replaceChildren(); if (target !== page) onPage(target);
  }
  jump.addEventListener('keydown', event => {if (event.key === 'Enter') {event.preventDefault(); go();}});
  const numbered = el('div', {className: 'pagination-controls page-numbers'});
  const visible = [...new Set([1, pages, ...Array.from({length: 5}, (_, index) => page - 2 + index).filter(value => value >= 1 && value <= pages)])].sort((a,b) => a-b);
  let previous = 0;
  for (const value of visible) {
    if (previous && value - previous > 1) numbered.append(el('span', {'aria-hidden': 'true'}, '…'));
    numbered.append(button(String(value), () => {if (value !== page) onPage(value);}, {
      'aria-label': `第 ${value} 页`, 'aria-current': value === page ? 'page' : null,
      className: value === page ? 'btn btn-primary' : 'btn'})); previous = value;
  }
  return el('nav', {className: 'numbered-pagination', 'aria-label': label},
    el('div', {className: 'numbered-pagination-row'}, el('span', {className: 'muted'}, `共 ${total} 条 · 第 ${page} / ${pages} 页`),
      el('label', {className: 'page-size-field'}, sizeLabel, sizeSelect)),
    el('div', {className: 'numbered-pagination-row'}, el('div', {className: 'pagination-controls'},
      button('首页', () => onPage(1), {disabled: page <= 1}), button('上一页', () => onPage(page-1), {disabled: page <= 1})),
      numbered, el('div', {className: 'pagination-controls'}, button('下一页', () => onPage(page+1), {disabled: page >= pages}), button('末页', () => onPage(pages), {disabled: page >= pages}))),
    el('div', {className: 'page-jump'}, el('label', {}, '跳至', jump, '页'), button('跳转', go)), errors);
}
