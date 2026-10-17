import {api} from '../api.js';
import {el, button, field, notice, pageHeading, showError, select, confirmAction} from '../ui.js';
import {profilePicker, profileReady, pollVisible} from './workflow-utils.js';
import {sourceSelection} from './source-selection.js';
import {processingHistory} from './processing-history.js';
import {batchPanel} from './processing-batch.js';
import {promptPicker} from './prompt-picker.js';
import {mount as mountDrafts} from './drafts.js';

export function mount(container, context) {
  if (context.id) return mountDrafts(container, context);
  const mountedHash = location.hash, controller = new AbortController();
  let disposed = false, busy = false, confirming = false, registry, history, batch, stopPoll, selection, model, template, detailRunning = false;
  const alive = () => !disposed && location.hash === mountedHash;
  async function settleCurrent(){while(!disposed&&!alive())await new Promise(resolve=>setTimeout(resolve,25));return alive();}
  const errors = el('div'), content = el('div', {}, notice('正在读取模型和模板…')), detail = el('div');
  container.append(pageHeading('AI 分析', '选择资料、模型与解析模板，主动提交逐篇或合并任务。生成结果请到独立草稿箱审阅。'), content, detail);
  async function initialize() {
    try {
      registry = await api('/api/v1/ai/profiles', {signal: controller.signal});
      if (!alive()) return;
      model = profilePicker(registry); model.dataset.testid = 'processing-profile';
      template = promptPicker({purpose: 'knowledge', alive, onChange: () => {context.setDirty(true); update();}});
      template.element.dataset.testid = 'processing-template';
      const mode = select([['individual','逐篇生成（每篇一份草稿）'],['merged','合并生成（全部资料一份草稿）']], 'individual'); mode.dataset.testid = 'processing-mode';
      const tokens = el('input', {type: 'number', min: 1, max: 131072, step: 1, required: true, value: 16384, 'data-testid': 'processing-max-tokens'});
      const timeout = el('input', {type: 'number', min: 0.01, max: 600, step: 'any', required: true, value: 180, 'data-testid': 'processing-timeout'});
      const info = el('div'), preview = el('div');
      selection = sourceSelection({alive, onChange: () => {context.setDirty(true); update();}});
      const generate = button('生成知识草稿', generateBatch, {className: 'btn btn-primary', disabled: true, 'data-testid': 'processing-generate'});
      function update() {
        const selected = selection.values(), count = selected.length;
        const limit = registry.max_input_chars, total = selected.reduce((sum,item)=>sum+(item.content_chars ?? Array.from(item.content || '').length),0);
        const tooLong = limit && (mode.value==='merged' ? total > limit : selected.some(item=>(item.content_chars ?? Array.from(item.content || '').length)>limit));
        const incompatible=mode.value==='merged'&&template.value()?.output_schema_version!==2;
        generate.disabled = busy || !count || !profileReady(registry, model.value) || !template.value() || incompatible || tooLong;
        info.replaceChildren(notice(incompatible?'合并生成需要 v2 输出模板，请切换模板。':`已选 ${count} 篇 · ${mode.value === 'merged' ? '合并为 1 份草稿，预计 1 次调用' : `逐篇生成，预计 ${count} 次调用`}。生成和预览不会创建知识笔记；采纳后才会写入。`));
        if (limit) info.append(notice(`正文共 ${total.toLocaleString('zh-CN')} 字符；${mode.value==='merged'?'合并总长度':'每篇正文'}上限 ${limit.toLocaleString('zh-CN')} 字符。${tooLong?'已超限，请减少选择或按说明调整输入限制并重启。':''}`,tooLong?'warning':'info'));
      }
      async function generateBatch() {
        if (!alive() || busy || confirming || generate.disabled || !tokens.reportValidity() || !timeout.reportValidity()) return;
        const sources = selection.values(), prompt = template.value(), calls = mode.value === 'merged' ? 1 : sources.length;
        if (sources.some(source => !Number.isInteger(source.version))) {errors.replaceChildren(notice('来源版本尚未读取完成，请稍后手动操作。', 'warning')); return;}
        confirming=true;
        const confirmed=await confirmAction(`将使用所选模型和模板，${mode.value === 'merged' ? '合并' : '逐篇'}处理 ${sources.length} 篇资料，预计最多 ${calls} 次模型调用，可能产生费用。失败不会自动重试。是否开始？`, {title: '确认模型调用', confirmLabel: '开始生成'});
        confirming=false;if(!confirmed||!alive())return;
        busy = true; selection.busy(true); template.busy(true); for (const input of [model, mode, tokens, timeout]) input.disabled = true; update(); errors.replaceChildren(notice('正在创建持久批次，请勿重复提交。'));
        const payload = {client_request_id: crypto.randomUUID(), mode: mode.value, sources: sources.map(source => ({source_id: source.id, expected_version: source.version})),
          prompt_template_id: prompt.id, prompt_template_version: prompt.version, generation_settings: {max_output_tokens: tokens.valueAsNumber, timeout_seconds: timeout.valueAsNumber}};
        if (model.value) payload.profile_id = model.value;
        try {
          const value = await api('/api/v1/processing/batches', {method: 'POST', body: payload});
          if (!await settleCurrent()) return; context.setDirty(false); context.navigate(`#/processing?batch_id=${value.id}`);
        } catch (error) {if (await settleCurrent()) {showError(error, errors); errors.append(notice('未自动重试。若请求断连，请先查看持久批次和处理记录，确认是否已创建后再操作。')); history?.refresh();}}
        finally {busy = false; if (alive()) {selection.busy(false); template.busy(false); for (const input of [model, mode, tokens, timeout]) input.disabled = false; update();}}
      }
      for (const input of [model, mode, tokens, timeout]) input.addEventListener('change', () => {context.setDirty(true); update();});
      history = processingHistory(registry, context, {alive, signal: controller.signal});
      content.replaceChildren(...[
        !registry.enabled && notice('AI 当前关闭；历史和草稿仍可查看。请在设置中启用并重启后生成。', 'warning'),
        registry.error_code && notice(`模型配置尚未就绪：${registry.error_code}`, 'warning'),
        el('section', {className: 'card stack'}, el('h2', {}, '生成新草稿'), selection.element,
          el('div', {className: 'form-grid'}, field('生成方式', mode), field('生成模型', model), field('解析提示词模板', template.element), field('输出 Token 上限', tokens), field('调用超时（秒）', timeout)),
          info, el('div', {className: 'processing-actions'}, generate),
          el('a', {href: '#/drafts'}, '打开草稿箱审阅生成结果 →'), errors)
      ].filter(Boolean));
      if (context.params.get('batch_id')) {batch = batchPanel(context.params.get('batch_id'), context, {alive}); content.append(batch.element);}
      content.append(history.element); await template.ready; update();
      const initial = context.params.get('source_id');
      if (initial) {try {const value = await api(`/api/v1/sources/${encodeURIComponent(initial)}`, {signal: controller.signal}); if (alive()) {selection.add(value,{notify:false});update();}} catch (error) {if (alive()) showError(error, errors);}}
      stopPoll = pollVisible(async () => {if (!alive()) return; await history.refresh(); if (batch) await batch.refresh();});
    } catch (error) {if (alive()) showError(error, content);}
  }
  initialize();
  return () => {disposed = true; controller.abort(); selection?.destroy(); template?.destroy(); batch?.dispose();stopPoll?.();};
}
