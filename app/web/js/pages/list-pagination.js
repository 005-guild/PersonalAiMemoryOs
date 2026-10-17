import {el} from '../ui.js';
import {numberedPagination, PAGE_SIZES} from './numbered-pagination.js';

// A list has its own state; navigating back never changes another list's page.
export function listState(key, defaults = {}) {
  let value;
  try {value = JSON.parse(sessionStorage.getItem(`memory-os:list:${key}`) || 'null');} catch {}
  const state = {...defaults, ...(value || {})};
  state.size = PAGE_SIZES.includes(Number(state.size)) ? Number(state.size) : 20;
  state.offset = Number.isSafeInteger(state.offset) && state.offset >= 0 ? state.offset : 0;
  return {value: state, save() {try {sessionStorage.setItem(`memory-os:list:${key}`, JSON.stringify(state));} catch {}}};
}

export function localPagination(items, render, {label = '记录分页', key = label} = {}) {
  const root = el('div', {className: 'stack'}), records = el('div'), paging = el('div');
  const saved = listState(key), state = saved.value;
  function draw() {
    const pages = Math.max(1, Math.ceil(items.length / state.size));
    state.offset = Math.min(state.offset, (pages - 1) * state.size); saved.save();
    records.replaceChildren(render(items.slice(state.offset, state.offset + state.size), state.offset));
    paging.replaceChildren(numberedPagination({total: items.length, page: Math.floor(state.offset / state.size) + 1, size: state.size, label,
      onPage: page => {state.offset = (page - 1) * state.size; draw();}, onSize: size => {state.size = size; state.offset = 0; draw();}}));
  }
  root.append(records, paging); root.refresh = draw; root.reveal = index => {state.offset = Math.floor(index / state.size) * state.size; draw();}; draw(); return root;
}
