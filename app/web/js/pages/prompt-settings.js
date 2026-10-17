import {api} from '../api.js';
import {el, button, field, notice, confirmAction, showError, select, renderMarkdown} from '../ui.js';
import {pager} from './workflow-utils.js';

/** Prompt changes are database revisions and take effect for new runs immediately. */
export function promptSettings(context, {alive, onDirty}) {
  const element = el('section', {className: 'card stack', 'data-testid': 'prompt-settings'}), list = el('div'), editor = el('div'), errors = el('div');
  const archived = el('input', {type: 'checkbox', 'data-testid': 'prompt-include-archived'});
  let current, dirty = false, busy = false, offset = 0, sequence = 0, controls, confirming=false, disposed=false;
  async function settleCurrent(){while(!disposed&&!alive())await new Promise(resolve=>setTimeout(resolve,25));return !disposed&&alive();}
  function setDirty(value) {dirty = value; onDirty(value);}
  async function mayDiscard() {return !dirty || await confirmAction('切换模板会丢弃当前模板尚未保存的修改。是否继续？', {title: '切换提示词模板', confirmLabel: '切换模板'});}
  element.append(el('div', {className: 'detail-header'}, el('h2', {}, '提示词模板'), button('＋ 新建模板', async () => {
    if (!busy && await mayDiscard() && alive()) edit(null);
  }, {'data-testid': 'prompt-new'})), notice('模板保存后立即供新生成任务使用，无需重启；不会调用模型。已有运行保留当时的模板快照。'),
  el('label', {className: 'settings-check'}, archived, '显示已归档模板'), errors, list, editor);
  archived.addEventListener('change', () => load(0));
  async function load(next = offset) {
    offset = next; const ticket = ++sequence;
    try {const page = await api(`/api/v1/prompt-templates?${new URLSearchParams({include_archived: String(archived.checked), offset, limit: '20'})}`);
      if (!alive() || ticket !== sequence) return;
      list.replaceChildren(el('div', {className: 'prompt-list'}, ...page.items.map(item => button(`${item.name} · v${item.version}${item.is_default ? ' · 默认' : ''}${item.archived_at ? ' · 已归档' : ''}`, async () => {
        if (!busy && await mayDiscard() && alive()) edit(item);
      }, {'data-testid': 'prompt-open'}))), pager(page, load));
    } catch (error) {if (alive() && ticket === sequence) showError(error, errors);}
  }
  function edit(value) {
    current = value; setDirty(false); errors.replaceChildren();
    const name = el('input', {value: value?.name || '', required: true, maxLength: 200, 'data-testid': 'prompt-name'});
    const description = el('textarea', {value: value?.description || '', maxLength: 2000, 'data-testid': 'prompt-description'});
    const content = el('textarea', {value: value?.content || '', required: true, maxLength: 100000, className: 'editor', 'data-testid': 'prompt-content'});
    const schema = select([['2','v2 · 完整正文与多来源引用'], ['1','v1 · 要点与观点']], String(value?.output_schema_version || 2)); schema.dataset.testid = 'prompt-schema';
    const preview = el('div'), revisions = el('div');
    const form = el('form', {className: 'stack prompt-editor', onSubmit: event => {event.preventDefault(); save();}});
    const saveButton = el('button', {type: 'submit', className: 'btn btn-primary', disabled: Boolean(value?.archived_at), 'data-testid': 'prompt-save'}, '保存模板');
    form.append(el('h3', {}, value ? `编辑模板 · v${value.version}` : '新建提示词模板'), field('模板名称', name), field('说明', description), field('输出格式', schema),
      field('提示词内容', content, '描述整理方法、风格和重点；结构化输出与安全约束仍由系统统一管理，不要填写密钥。'),
      el('div', {className: 'page-actions'}, saveButton, button('预览内容', () => preview.replaceChildren(renderMarkdown(content.value))),
        button('复制为新模板', () => {if (!busy) {current = null; name.value = `${name.value}（副本）`; saveButton.disabled = false; name.disabled=false; content.disabled = false; description.disabled = false; schema.disabled = false; setDirty(true);}} , {'data-testid': 'prompt-copy'}),
        value && !value.archived_at && button('设为默认', () => mutation('default'), {disabled: value.is_default, 'data-testid': 'prompt-default'}),
        value && !value.archived_at && button('归档模板', () => mutation('archive'), {'data-testid': 'prompt-archive'}),
        value && button('查看修订历史', async () => {try {const result = await api(`/api/v1/prompt-templates/${value.id}/revisions`); if (alive()) revisions.replaceChildren(...result.items.map(item => el('details', {}, el('summary', {}, `v${item.version} · ${item.name}`), el('pre', {className: 'snapshot'}, item.content))));} catch (error) {if (alive()) showError(error, errors);}})), preview, revisions);
    form.addEventListener('input', () => setDirty(true)); form.addEventListener('change', () => setDirty(true));
    if (value?.archived_at) {for (const input of [name, description, content, schema]) input.disabled = true; form.prepend(notice('已归档模板保留供历史查看，可复制为新模板。'));}
    controls = form;
    editor.replaceChildren(form);
    async function save() {
      if (busy || !alive() || !form.reportValidity()) return;
      const body = {name: name.value, description: description.value, content: content.value, output_schema_version: Number(schema.value)};
      if (current) body.expected_version = current.version;
      await write(current ? `/api/v1/prompt-templates/${current.id}` : '/api/v1/prompt-templates', current ? 'PATCH' : 'POST', body);
    }
  }
  async function mutation(action) {
    if (busy || confirming || !current || !alive()) return;
    confirming=true;
    if(!await mayDiscard()||!alive()){confirming=false;return;}
    const confirmed=await confirmAction(action === 'archive' ? '归档后不能用于新生成；历史草稿仍保留。是否归档？' : '将此模板设为默认？后续新生成使用新的默认模板，无需重启。', {title: '提示词模板', confirmLabel: action === 'archive' ? '归档' : '设为默认'});
    confirming=false;if(!confirmed||!alive())return;
    await write(`/api/v1/prompt-templates/${current.id}/${action}`, 'POST', {expected_version: current.version});
  }
  async function write(path, method, body) {
    busy = true; errors.replaceChildren(); const previous = [...element.querySelectorAll('input,select,textarea,button')].map(node => [node,node.disabled]); previous.forEach(([node]) => node.disabled = true);
    try {const saved = await api(path, {method, body}); if (!await settleCurrent()) return; edit(saved); errors.replaceChildren(notice('模板已保存，新生成任务立即可用；没有调用模型。', 'success')); await load();}
    catch (error) {if (await settleCurrent()) {showError(error, errors); if (error.status === 409) errors.append(button('重新读取该模板', async () => {
      if (!current || !await mayDiscard() || !alive()) return;
      try {const fresh = await api(`/api/v1/prompt-templates/${current.id}`); if (alive()) edit(fresh);} catch (error) {if (alive()) showError(error, errors);}
    }));}}
    finally {busy = false; if (alive()) for (const [node,disabled] of previous) if (node.isConnected) node.disabled = disabled;}
  }
  load(); return {element, dispose: () => {disposed=true;sequence++; current = null; controls = null;}};
}
