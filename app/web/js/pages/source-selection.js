import {api} from '../api.js';
import {el, button, field, notice, renderMarkdown, debounce, showError} from '../ui.js';
import {numberedPagination} from './numbered-pagination.js';

/** A bounded selection of individual sources; bodies are fetched only for preview. */
export function sourceSelection({initial = [], onChange = () => {}, alive = () => true, max = 20, testId = 'processing', preview = true} = {}) {
  const selected = new Map(initial.map(item => [typeof item === 'string' ? item : item.id, typeof item === 'string' ? {id: item, title: item} : item]));
  const search = el('input', {type: 'search', placeholder: '搜索资料标题…', 'aria-label': '搜索来源资料', 'data-testid': `${testId}-source-search`});
  const feedback = el('div'), results = el('div'), paging = el('div'), chosen = el('div'), reader = el('div');
  const all = el('input', {type: 'checkbox', 'aria-label': '选择当前页来源', 'data-testid': `${testId}-source-all`});
  const clear = button('清空已选', () => {if (locked) return; selected.clear(); changed();}, {'data-testid': `${testId}-source-clear`});
  const root = el('div', {className: 'stack source-selection', 'data-testid': `${testId}-sources`},
    field('查找资料', search, `跨页保留选择，最多 ${max} 篇；只在主动生成时调用模型。`),
    el('div', {className: 'selection-bar'}, el('label', {className: 'settings-check'}, all, '当前页全选'), clear, chosen), feedback, results, paging, reader);
  let page = 1, size = 20, rows = [], sequence = 0, previewSequence = 0, stopped = false, locked = false, controller, previewController;
  const disabledControls=new Map();
  function lockControls() {for(const node of root.querySelectorAll('input,select,button')){if(!disabledControls.has(node))disabledControls.set(node,node.disabled);node.disabled=true;}}
  const current = () => !stopped && alive();
  function changed() {drawSelection(); onChange([...selected.values()]);}
  function drawSelection() {
    chosen.replaceChildren(el('strong', {}, `已选 ${selected.size} / ${max} 篇`), ...[...selected.values()].map(item => button(`${item.title} ×`, () => {
      if (!locked) {selected.delete(item.id); changed();}
    }, {className: 'btn source-chip', disabled: locked, 'aria-label': `取消选择 ${item.title}`})));
    const active = rows.filter(item => !item.deleted_at), count = active.filter(item => selected.has(item.id)).length;
    all.checked = active.length > 0 && count === active.length; all.indeterminate = count > 0 && count < active.length;
    all.disabled = locked || !active.length; clear.disabled = locked || !selected.size;
    for (const box of results.querySelectorAll('input[data-source-id]')) {box.checked = selected.has(box.dataset.sourceId); box.disabled = locked || Boolean(rows.find(item => item.id === box.dataset.sourceId)?.deleted_at);}
  }
  function toggle(item, checked) {
    if (locked || !current()) return;
    if (checked && !selected.has(item.id) && selected.size >= max) {feedback.replaceChildren(notice(`最多选择 ${max} 篇，请先取消其他资料。`, 'warning')); drawSelection(); return;}
    if (checked) selected.set(item.id, item); else selected.delete(item.id);
    changed();
  }
  all.addEventListener('change', () => {
    if (locked || !current()) return;
    const active = rows.filter(item => !item.deleted_at);
    if (all.checked && selected.size + active.filter(item => !selected.has(item.id)).length > max) {feedback.replaceChildren(notice(`当前页全选将超过 ${max} 篇，请先清空或逐项选择。`, 'warning')); drawSelection(); return;}
    for (const item of active) if (all.checked) selected.set(item.id, item); else selected.delete(item.id);
    changed();
  });
  async function showPreview(item) {
    if (!current()) return;
    const ticket = ++previewSequence; previewController?.abort(); previewController = new AbortController();
    reader.replaceChildren(notice('正在读取完整正文…'));
    try {
      const value = await api(`/api/v1/sources/${encodeURIComponent(item.id)}?include_deleted=true`, {signal: previewController.signal});
      if (!current() || ticket !== previewSequence) return;
      const content = value.content?.length > 100000 ? el('textarea', {value: value.content, readOnly: true, className: 'editor', 'aria-label': '完整来源正文'}) : renderMarkdown(value.content || '');
      reader.replaceChildren(el('section', {className: 'source-selection-preview stack'}, el('div', {className: 'detail-header'},
        el('h3', {}, value.title), button('关闭预览', () => {previewSequence++; previewController?.abort(); reader.replaceChildren();})),
        el('p', {className: 'muted'}, `${value.author || '未署名'} · v${value.version}`),
        selected.has(item.id) && selected.get(item.id).version !== value.version && notice('来源版本已变化。请取消后重新选择此资料，确认新版本后再生成。', 'warning'), content));
    } catch (error) {if (current() && ticket === previewSequence) showError(error, reader);}
  }
  async function load() {
    controller?.abort(); controller = new AbortController(); const ticket = ++sequence;
    try {
      const value = await api(`/api/v1/ui/sources?${new URLSearchParams({state: 'active', q: search.value, offset: String((page-1)*size), limit: String(size)})}`, {signal: controller.signal});
      if (!current() || ticket !== sequence) return;
      if (page > 1 && (page-1)*size >= value.total) {page = Math.max(1, Math.ceil(value.total/size)); return load();}
      rows = value.items;
      results.replaceChildren(el('div', {className: 'table-wrap'}, el('table', {className: 'data-table'},
        el('thead', {}, el('tr', {}, ...['选择', '资料标题', '作者 / 类型', ...(preview ? ['正文'] : [])].map(text => el('th', {}, text)))),
        el('tbody', {}, ...rows.map(item => {
          const box = el('input', {type: 'checkbox', 'data-source-id': item.id, 'aria-label': `选择来源 ${item.title}`, onChange: event => toggle(item, event.target.checked)});
          return el('tr', {}, el('td', {}, box), el('td', {}, el('strong', {}, item.title), el('small', {className: 'record-excerpt'}, item.excerpt || '')),
            el('td', {}, item.author || '未署名', el('small', {className: 'status-detail'}, `${item.source_type} · ${item.content_chars ?? '未知'} 字符`)), preview && el('td', {}, button('预览正文', () => showPreview(item))));
        })))));
      if (!rows.length) results.append(notice('没有匹配的正常资料。'));
      paging.replaceChildren(numberedPagination({total: value.total, page, size, sizeLabel: '来源每页条数', label: '来源资料分页', onPage: value => {if (!locked) {page = value; load();}}, onSize: value => {if (!locked) {size = value; page = 1; load();}}}));
      if(locked)lockControls();
      drawSelection();
    } catch (error) {if (current() && ticket === sequence) showError(error, feedback);}
  }
  const delayed = debounce(() => {page = 1; load();});let composing=false;
  search.addEventListener('compositionstart',()=>{composing=true;delayed.cancel();});
  search.addEventListener('compositionend',()=>{composing=false;delayed();});
  search.addEventListener('input',()=>{if(!composing)delayed();}); load(); drawSelection();
  // Resolve existing associations without discarding deleted or missing references.
  for (const item of initial) {
    const id = typeof item === 'string' ? item : item.id;
    if (typeof item !== 'string') continue;
    api(`/api/v1/sources/${encodeURIComponent(id)}?include_deleted=true`).then(value => {
      if (current() && selected.has(id)) {selected.set(id, value); drawSelection();}
    }).catch(() => {});
  }
  return {element: root, values: () => [...selected.values()], ids: () => [...selected.keys()],
    add: (value,{notify=true}={}) => {if (current() && !selected.has(value.id) && selected.size < max) {selected.set(value.id, value);drawSelection();if(notify)onChange([...selected.values()]);}},
    busy: value => {locked=value;if(value)lockControls();else{for(const[node,disabled]of disabledControls)if(node.isConnected)node.disabled=disabled;disabledControls.clear();}drawSelection();},
    destroy: () => {stopped = true; controller?.abort(); previewController?.abort(); delayed.cancel(); selected.clear();}};
}
