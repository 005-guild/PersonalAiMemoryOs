import {api} from '../api.js';
import {el, button, field, notice, confirmAction, showError, select, renderMarkdown, debounce} from '../ui.js';
import {pager} from './workflow-utils.js';
import {listState} from './list-pagination.js';

export function promptSettings(context, {alive, onDirty}) {
  const element = el('section', {className: 'card stack', 'data-testid': 'prompt-settings'}), list = el('div'), editor = el('div'), errors = el('div');
  const stored = listState('prompt-center', {purpose: 'knowledge', q: '', archived: false}), state = stored.value;
  const purpose = select([['knowledge','笔记解析'],['rag_qa','RAG 问答']], state.purpose); purpose.setAttribute('aria-label', '模板用途');
  const archived = el('input', {type: 'checkbox', checked: state.archived, 'data-testid': 'prompt-include-archived'});
  const search = el('input', {type: 'search', value: state.q, placeholder: '按模板名称搜索', 'aria-label': '搜索提示词模板'});
  let current, dirty = false, busy = false, sequence = 0, editorSequence = 0, confirming = false, disposed = false;
  const active = () => !disposed && alive();
  async function settle() {while (!disposed && !alive()) await new Promise(resolve => setTimeout(resolve, 25)); return active();}
  function setDirty(value) {dirty = value; onDirty(value);}
  async function discard() {return !dirty || await confirmAction('切换模板会丢弃尚未保存的修改，是否继续？', {title: '切换提示词模板', confirmLabel: '继续'});}
  element.append(el('div', {className: 'detail-header'}, el('h2', {}, '提示词模板'), button('＋ 新建模板', async () => {if (!busy && await discard() && active()) edit(null);}, {'data-testid': 'prompt-new'})),
    notice('笔记解析与 RAG 问答各有独立默认模板。保存立即供新请求使用，不需重启、不调用模型；已提交任务保留冻结快照。'),
    el('div', {className: 'toolbar'}, field('模板用途', purpose), search, el('label', {className: 'settings-check'}, archived, '显示已归档')), errors, list, editor);
  purpose.addEventListener('change', async () => {if (busy || !await discard() || !active()) {purpose.value = state.purpose; return;} state.purpose = purpose.value; state.offset = 0; current = null; editorSequence++; editor.replaceChildren(); setDirty(false); load();});
  archived.addEventListener('change', () => load(0)); const delayed = debounce(() => load(0)); search.addEventListener('input', delayed);
  async function open(item) {
    if (busy || !await discard() || !active()) return;
    const ticket = ++editorSequence;
    try {const full = await api(`/api/v1/prompt-templates/${item.id}`); if (active() && ticket === editorSequence) edit(full);}
    catch (error) {if (active() && ticket === editorSequence) showError(error, errors);}
  }
  async function load(next = state.offset, size = state.size) {
    Object.assign(state, {offset: next, size, q: search.value, archived: archived.checked}); stored.save(); const ticket = ++sequence;
    try {const page = await api(`/api/v1/prompt-templates?${new URLSearchParams({purpose: state.purpose, q: state.q, include_archived: state.archived, summary_only: 'true', offset: state.offset, limit: state.size})}`);
      if (!active() || ticket !== sequence) return;
      if (state.offset && state.offset >= page.total) return load(Math.max(0, Math.floor((page.total-1)/state.size)*state.size));
      list.replaceChildren(el('div', {className: 'prompt-list'}, ...page.items.map(item => button(`${item.name} · v${item.version}${item.is_default ? ' · 默认' : ''}${item.archived_at ? ' · 已归档' : ''}`, () => open(item), {'data-testid': 'prompt-open'}))), pager(page, load, '提示词模板分页'));
      if (!page.total) list.prepend(notice('没有匹配模板，可以新建。'));
    } catch (error) {if (active() && ticket === sequence) showError(error, errors);}
  }
  function edit(value) {
    current = value; setDirty(false); editorSequence++; const ticket = editorSequence; errors.replaceChildren();
    const name = el('input', {value: value?.name || '', required: true, maxLength: 200, 'data-testid': 'prompt-name'});
    const description = el('textarea', {value: value?.description || '', maxLength: 2000, 'data-testid': 'prompt-description'});
    const content = el('textarea', {value: value?.content || '', required: true, maxLength: 100000, className: 'editor', 'data-testid': 'prompt-content'});
    const schema = select([['2','v2 · 完整正文与多来源引用'],['1','v1 · 要点与观点']], String(value?.output_schema_version || 2)); schema.dataset.testid = 'prompt-schema';
    const preview = el('div'), revisions = el('div'), revisionState = listState(`prompt-revisions:${value?.id || 'new'}`);let revisionSequence=0;
    const form = el('form', {className: 'stack prompt-editor', onSubmit: event => {event.preventDefault(); save();}});
    const saveButton = el('button', {type: 'submit', className: 'btn btn-primary', disabled: Boolean(value?.archived_at), 'data-testid': 'prompt-save'}, '保存模板');
    form.append(el('h3', {}, value ? `编辑模板 · v${value.version}` : '新建提示词模板'), field('用途', el('strong', {}, state.purpose === 'rag_qa' ? 'RAG 问答' : '笔记解析')),
      field('模板名称', name), field('说明', description), state.purpose === 'knowledge' && field('输出格式', schema),
      field('提示词内容', content, state.purpose === 'rag_qa' ? '定制回答风格、结构与重点。仅依据检索资料、证据不足说明及引用校验仍由系统固定执行。' : '描述整理方法、风格与重点；共同结构化输出约束仍由系统管理。不要填写密钥。'),
      el('div', {className: 'page-actions'}, saveButton, button('预览内容', () => preview.replaceChildren(renderMarkdown(content.value))),
        button('复制为新模板', () => {if (busy) return; current = null; name.value += '（副本）'; for (const node of [name,description,content,schema,saveButton]) node.disabled = false; setDirty(true);}, {'data-testid': 'prompt-copy'}),
        value && !value.archived_at && button('设为默认', () => mutation('default'), {disabled: value.is_default, 'data-testid': 'prompt-default'}),
        value && !value.archived_at && button('归档模板', () => mutation('archive'), {'data-testid': 'prompt-archive'}),
        value && button('查看修订历史', () => loadRevisions())), preview, revisions);
    async function loadRevisions(offset = revisionState.value.offset, size = revisionState.value.size) {
      const revisionTicket=++revisionSequence;
      Object.assign(revisionState.value, {offset, size}); revisionState.save();
      try {const result = await api(`/api/v1/prompt-templates/${value.id}/revisions?${new URLSearchParams({offset, limit: size, summary_only: 'true'})}`);
        if (!active() || ticket !== editorSequence || revisionTicket!==revisionSequence) return;
        revisions.replaceChildren(...result.items.map(item => {
          const block = el('details', {}, el('summary', {}, `v${item.version} · ${item.name}`)); let requested = false;
          block.addEventListener('toggle', async () => {if (!block.open || requested) return; requested = true;
            try {const full = await api(`/api/v1/prompt-templates/${value.id}/revisions/${item.version}`); if (active() && ticket === editorSequence && block.isConnected) block.append(el('pre', {className: 'snapshot'}, full.content));}
            catch (error) {requested = false; if (active() && ticket === editorSequence) showError(error, errors);}}); return block;
        }), pager(result, loadRevisions, '模板修订历史分页'));
      } catch (error) {if (active() && ticket === editorSequence && revisionTicket===revisionSequence) showError(error, errors);}
    }
    form.addEventListener('input', () => setDirty(true)); form.addEventListener('change', () => setDirty(true));
    if (value?.archived_at) {for (const node of [name,description,content,schema]) node.disabled = true; form.prepend(notice('已归档模板只能查看历史或复制。'));}
    editor.replaceChildren(form);
    async function save() {
      if (busy || !active() || !form.reportValidity()) return;
      const body = {name: name.value, description: description.value, content: content.value, output_schema_version: state.purpose === 'rag_qa' ? 1 : Number(schema.value)};
      if (current) body.expected_version = current.version; else body.purpose = state.purpose;
      await write(current ? `/api/v1/prompt-templates/${current.id}` : '/api/v1/prompt-templates', current ? 'PATCH' : 'POST', body);
    }
  }
  async function mutation(action) {
    if (busy || confirming || !current || !active()) return; confirming = true;
    if (!await discard() || !active()) {confirming = false; return;}
    const confirmed = await confirmAction(action === 'archive' ? '归档后不能用于新请求，历史快照保留。是否归档？' : '设为这一用途的默认模板？', {title: '提示词模板', confirmLabel: action === 'archive' ? '归档' : '设为默认'});
    confirming = false; if (confirmed && active()) await write(`/api/v1/prompt-templates/${current.id}/${action}`, 'POST', {expected_version: current.version});
  }
  async function write(path, method, body) {
    busy = true; const previous = [...element.querySelectorAll('input,select,textarea,button')].map(node => [node,node.disabled]); previous.forEach(([node]) => node.disabled = true);
    try {const saved = await api(path, {method, body}); if (!await settle()) return; edit(saved); errors.replaceChildren(notice('模板已保存，新请求立即可用；没有调用模型。', 'success')); await load();}
    catch (error) {if (await settle()) {showError(error, errors); if (error.status === 409) errors.append(button('重新读取模板', () => current && open(current)));}}
    finally {busy = false; if (active()) for (const [node, disabled] of previous) if (node.isConnected) node.disabled = disabled;}
  }
  load(); return {element, dispose() {disposed = true; sequence++; editorSequence++; delayed.cancel();}};
}
