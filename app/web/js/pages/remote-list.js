import {api} from '../api.js';
import {el, button, notice, showError} from '../ui.js';
import {pager} from './workflow-utils.js';
import {listState} from './list-pagination.js';

export function remoteList(endpoint, render, {label, key = endpoint, alive = () => true, signal, params = {}, emptyText = '暂无记录。'} = {}) {
  const saved = listState(key), state = saved.value, element = el('div', {className: 'stack'}), rows = el('div'), errors = el('div'); let sequence = 0;
  async function load(offset = state.offset, size = state.size) {
    Object.assign(state, {offset, size}); saved.save(); const ticket = ++sequence;
    try {const query = new URLSearchParams({...params, offset, limit: size});const page = await api(`${endpoint}?${query}`, {signal});
      if (!alive() || ticket !== sequence) return;
      if (offset && offset >= page.total) return load(Math.max(0, Math.floor((page.total-1)/size)*size));
      rows.replaceChildren(page.items.length ? render(page.items, offset) : notice(emptyText), pager(page, load, label)); errors.replaceChildren();
    } catch (error) {if (alive() && ticket === sequence) showError(error, errors);}
  }
  element.append(el('div', {className: 'detail-header'}, el('h3', {}, label), button('刷新列表', () => load())), errors, rows);
  const ready = load(); return {element, ready, refresh: () => load()};
}
