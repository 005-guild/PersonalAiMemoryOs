import {api} from '../api.js';
import {el, button, field, notice, pageHeading, showError, select, confirmAction} from '../ui.js';
import {profilePicker, profileReady, pollVisible} from './workflow-utils.js';
import {sourceSelection} from './source-selection.js';
import {processingHistory} from './processing-history.js';
import {batchPanel} from './processing-batch.js';
import {renderRun} from './processing-detail.js';

export function mount(container, context) {
  const mountedHash = location.hash, controller = new AbortController();
  let disposed = false, busy = false, confirming = false, registry, templates = [], history, batch, stopPoll, selection, model, template, detailRunning = false;
  const alive = () => !disposed && location.hash === mountedHash;
  async function settleCurrent(){while(!disposed&&!alive())await new Promise(resolve=>setTimeout(resolve,25));return alive();}
  const errors = el('div'), content = el('div', {}, notice('正在读取模型和模板…')), detail = el('div');
  container.append(pageHeading('AI 草稿', '选择多篇资料，逐篇生成或合并整理；先预览，再人工采纳。模型只在确认后调用。'), content, detail);
  async function loadDetail() {
    if (!context.id) return;
    try {const run = await api(`/api/v1/processing/runs/${encodeURIComponent(context.id)}`, {signal: controller.signal});
      if (!alive()) return; detailRunning = run.status === 'running'; detail.replaceChildren(renderRun(run, context, {alive, onRefresh: loadDetail}));
    } catch (error) {if (alive()) showError(error, detail);}
  }
  async function initialize() {
    try {
      const [profiles, prompts] = await Promise.all([api('/api/v1/ai/profiles', {signal: controller.signal}), api('/api/v1/prompt-templates?limit=100&offset=0', {signal: controller.signal})]);
      if (!alive()) return; registry = profiles; templates = prompts.items;
      model = profilePicker(registry); model.dataset.testid = 'processing-profile';
      template = select(templates.map(item => [item.id, `${item.name} · v${item.version} · 格式 v${item.output_schema_version}${item.is_default ? ' · 默认' : ''}`]), templates.find(item => item.is_default)?.id || templates[0]?.id);
      template.dataset.testid = 'processing-template'; template.setAttribute('aria-label', '生成提示词模板');
      const mode = select([['individual','逐篇生成（每篇一份草稿）'],['merged','合并生成（全部资料一份草稿）']], 'individual'); mode.dataset.testid = 'processing-mode';
      const tokens = el('input', {type: 'number', min: 1, max: 131072, step: 1, required: true, value: 16384, 'data-testid': 'processing-max-tokens'});
      const timeout = el('input', {type: 'number', min: 0.01, max: 600, step: 'any', required: true, value: 180, 'data-testid': 'processing-timeout'});
      const info = el('div'), preview = el('div');
      selection = sourceSelection({alive, onChange: () => {context.setDirty(true); update();}});
      const generate = button('生成知识草稿', generateBatch, {className: 'btn btn-primary', disabled: true, 'data-testid': 'processing-generate'});
      function update() {
        const count = selection.values().length;
        const incompatible=mode.value==='merged'&&templates.find(item=>item.id===template.value)?.output_schema_version!==2;
        generate.disabled = busy || !count || !profileReady(registry, model.value) || !template.value || incompatible;
        info.replaceChildren(notice(incompatible?'合并生成需要 v2 输出模板，请切换模板。':`已选 ${count} 篇 · ${mode.value === 'merged' ? '合并为 1 份草稿，预计 1 次调用' : `逐篇生成，预计 ${count} 次调用`}。生成和预览不会创建知识笔记；采纳后才会写入。`));
      }
      function showTemplate() {
        const item = templates.find(item => item.id === template.value);
        preview.replaceChildren(item ? el('details', {}, el('summary', {}, `预览模板：${item.name}`), el('pre', {className: 'snapshot'}, item.content)) : notice('请先在设置中创建可用模板。', 'warning'));
      }
      async function generateBatch() {
        if (!alive() || busy || confirming || generate.disabled || !tokens.reportValidity() || !timeout.reportValidity()) return;
        const sources = selection.values(), prompt = templates.find(item => item.id === template.value), calls = mode.value === 'merged' ? 1 : sources.length;
        if (sources.some(source => !Number.isInteger(source.version))) {errors.replaceChildren(notice('来源版本尚未读取完成，请稍后手动操作。', 'warning')); return;}
        confirming=true;
        const confirmed=await confirmAction(`将使用所选模型和模板，${mode.value === 'merged' ? '合并' : '逐篇'}处理 ${sources.length} 篇资料，预计最多 ${calls} 次模型调用，可能产生费用。失败不会自动重试。是否开始？`, {title: '确认模型调用', confirmLabel: '开始生成'});
        confirming=false;if(!confirmed||!alive())return;
        busy = true; selection.busy(true); for (const input of [model, template, mode, tokens, timeout]) input.disabled = true; update(); errors.replaceChildren(notice('正在创建持久批次，请勿重复提交。'));
        const payload = {client_request_id: crypto.randomUUID(), mode: mode.value, sources: sources.map(source => ({source_id: source.id, expected_version: source.version})),
          prompt_template_id: prompt.id, prompt_template_version: prompt.version, generation_settings: {max_output_tokens: tokens.valueAsNumber, timeout_seconds: timeout.valueAsNumber}};
        if (model.value) payload.profile_id = model.value;
        try {
          const value = await api('/api/v1/processing/batches', {method: 'POST', body: payload});
          if (!await settleCurrent()) return; context.setDirty(false); context.navigate(`#/processing?batch_id=${value.id}`);
        } catch (error) {if (await settleCurrent()) {showError(error, errors); errors.append(notice('未自动重试。若请求断连，请先查看持久批次和处理记录，确认是否已创建后再操作。')); history?.refresh();}}
        finally {busy = false; if (alive()) {selection.busy(false); for (const input of [model, template, mode, tokens, timeout]) input.disabled = false; update();}}
      }
      for (const input of [model, template, mode, tokens, timeout]) input.addEventListener('change', () => {context.setDirty(true); update();});
      template.addEventListener('change', showTemplate);
      history = processingHistory(registry, context, {alive, signal: controller.signal});
      content.replaceChildren(...[
        !registry.enabled && notice('AI 当前关闭；历史和草稿仍可查看。请在设置中启用并重启后生成。', 'warning'),
        registry.error_code && notice(`模型配置尚未就绪：${registry.error_code}`, 'warning'),
        el('section', {className: 'card stack'}, el('h2', {}, '生成新草稿'), selection.element,
          el('div', {className: 'form-grid'}, field('生成方式', mode), field('生成模型', model), field('提示词模板', template), field('输出 Token 上限', tokens), field('调用超时（秒）', timeout)),
          preview, info, el('div', {className: 'processing-actions'}, generate, history.statusField),
          el('small', {className: 'muted'}, '记录状态只筛选历史，切换后不会改变本次来源、模型或模板选择。'), errors)
      ].filter(Boolean));
      if (context.params.get('batch_id')) {batch = batchPanel(context.params.get('batch_id'), context, {alive}); content.append(batch.element);}
      content.append(history.element); showTemplate(); update();
      const initial = context.params.get('source_id');
      if (initial) {try {const value = await api(`/api/v1/sources/${encodeURIComponent(initial)}`, {signal: controller.signal}); if (alive()) {selection.add(value,{notify:false});update();}} catch (error) {if (alive()) showError(error, errors);}}
      stopPoll = pollVisible(async () => {if (!alive()) return; await history.refresh(); if (batch) await batch.refresh(); if (detailRunning) await loadDetail();});
    } catch (error) {if (alive()) showError(error, content);}
  }
  initialize(); loadDetail();
  return () => {disposed = true; controller.abort(); selection?.destroy(); batch?.dispose();stopPoll?.();};
}
