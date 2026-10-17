import {api} from '../api.js';
import {el, button, notice, showError, debounce, renderMarkdown} from '../ui.js';
import {pager} from './workflow-utils.js';

/** Paginated summaries never cap template choice at the first 100 records. */
export function promptPicker({purpose = 'knowledge', alive = () => true, onChange = () => {}} = {}) {
  const element = el('div', {className: 'stack prompt-picker'}), selected = el('div'), list = el('div'), errors = el('div');
  const search = el('input', {type: 'search', placeholder: '搜索模板名称…', 'aria-label': purpose === 'rag_qa' ? '搜索问答模板' : '搜索解析模板'});
  let current, offset = 0, size = 20, sequence = 0, selectionSequence = 0, stopped = false, locked = false, controller;
  const disabledStates = new Map();
  const active = () => !stopped && alive();
  function drawSelected() {selected.replaceChildren(current ? el('details', {}, el('summary', {}, `已选：${current.name} · v${current.version}`), renderMarkdown(current.content)) : notice('尚未选择模板。'));}
  async function choose(item, notify = true) {
    const ticket = ++selectionSequence;
    try {const full = await api(`/api/v1/prompt-templates/${encodeURIComponent(item.id)}`);
      if (!active() || ticket !== selectionSequence) return;
      if (full.archived_at || full.purpose !== purpose) {errors.replaceChildren(notice('该模板已经归档或用途不匹配，请重新选择。', 'warning')); return;}
      current = full; drawSelected(); element.dispatchEvent(new Event('change')); if (notify) onChange(full);
    } catch (error) {if (active() && ticket === selectionSequence) showError(error, errors);}
  }
  async function load(next = offset, nextSize = size) {
    offset = next; size = nextSize; controller?.abort(); controller = new AbortController(); const ticket = ++sequence;
    try {const page = await api(`/api/v1/prompt-templates?${new URLSearchParams({purpose, q: search.value, summary_only: 'true', offset, limit: size})}`, {signal: controller.signal});
      if (!active() || ticket !== sequence) return;
      if (offset && offset >= page.total) return load(Math.max(0, Math.floor((page.total - 1) / size) * size));
      list.replaceChildren(el('div', {className: 'prompt-list'}, ...page.items.map(item => button(`${item.name} · v${item.version}${item.is_default ? ' · 默认' : ''}`, () => {if (!locked) choose(item);}, {'data-template-id': item.id}))),
        pager(page, load, `${purpose === 'rag_qa' ? '问答' : '解析'}模板选择分页`));
      if (!current && !search.value && page.items.length) await choose(page.items.find(item => item.is_default) || page.items[0], false);
      if (!page.total) list.prepend(notice('没有匹配模板，请到提示词中心新建。'));
      busy(locked);
    } catch (error) {if (active() && ticket === sequence) showError(error, errors);}
  }
  const delayed = debounce(() => load(0)); search.addEventListener('input', delayed);
  function busy(value) {
    locked = value;
    if (value) {for (const node of element.querySelectorAll('button,input,select')) {if (!disabledStates.has(node)) disabledStates.set(node,node.disabled);node.disabled=true;}}
    else {for (const [node,disabled] of disabledStates) node.disabled=disabled;disabledStates.clear();}
  }
  element.append(search, selected, errors, list); const ready = load();
  return {element, ready, value: () => current, busy, destroy() {stopped = true; sequence++; selectionSequence++; controller?.abort(); delayed.cancel();}};
}
