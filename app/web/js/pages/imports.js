import {api} from '../api.js';
import {el, button, field, notice, empty, pageHeading, showError} from '../ui.js';
import {MAX_IMPORT_BYTES, markdownSelection, readMarkdownSelection} from './import-files.js';
import {publicImportReport, showImportReport} from './import-report.js';

export async function mount(container, context) {
  let mode = 'json', bytes = null, filename = '', previewed = false, busy = false, reading = false, selection = 0, stopped = false, report = null;
  let localReadErrors = [];
  const errors = el('div'), localIssues = el('div', {'data-testid': 'import-local-errors'});
  const chosen = el('p', {className: 'muted'}, '尚未选择文件');
  const result = el('div', {'data-testid': 'import-report'}, empty('先预演，再导入', '系统会逐项校验；重复资料只报告差异，不覆盖已有资料。'));
  const input = el('input', {type: 'file', accept: '.json,application/json', 'aria-label': '选择知乎 JSON 文件', 'data-testid': 'import-file'});
  const directory = el('input', {type: 'file', webkitdirectory: true, multiple: true, 'aria-label': '选择知乎 Markdown 文件夹', 'data-testid': 'import-directory'});
  const multiple = el('input', {type: 'file', multiple: true, accept: '.md,text/markdown', 'aria-label': '多选知乎 Markdown 文件', 'data-testid': 'import-markdown-files'});
  const jsonTab = button('协议 JSON', () => switchMode('json'), {role: 'tab', id: 'import-json-tab', 'aria-controls': 'import-json-panel', 'aria-selected': 'true', className: 'btn active'});
  const markdownTab = button('知乎 Markdown 文件夹', () => switchMode('markdown'), {role: 'tab', id: 'import-markdown-tab', 'aria-controls': 'import-markdown-panel', 'aria-selected': 'false', tabIndex: -1});
  const jsonPanel = el('section', {role: 'tabpanel', id: 'import-json-panel', 'aria-labelledby': 'import-json-tab'}, field('知乎协议 JSON 文件', input, 'UTF-8（支持 BOM）· 最多 10 MiB / 500 条'));
  const markdownPanel = el('section', {role: 'tabpanel', id: 'import-markdown-panel', 'aria-labelledby': 'import-markdown-tab', hidden: true, className: 'stack'},
    field('选择导出目录（包含子目录）', directory, '仅导入 .md；跳过 README.md、图片和导出进度 JSON。'),
    field('或多选 Markdown 文件', multiple, '兼容目录选择不可用的环境；最多 1,000 个 MD / 10 MiB，请勿仅修改文件扩展名。'),
    notice('仅创建原始资料 Source；不会生成 Knowledge 笔记、调用 AI 或复制和展示图片。'));
  const preview = button('预演文件', () => send(true), {className: 'btn btn-primary', disabled: true, 'data-testid': 'import-preview'});
  const submit = button('提交导入', () => send(false), {disabled: true, 'data-testid': 'import-submit'});
  function update() {
    for (const control of [input, directory, multiple, jsonTab, markdownTab]) control.disabled = busy;
    preview.disabled = busy || reading || !bytes; submit.disabled = busy || reading || !previewed;
  }
  function reset() {
    selection++; bytes = null; previewed = false; report = null; reading = false; filename = ''; localReadErrors = [];
    errors.replaceChildren(); localIssues.replaceChildren(); result.replaceChildren(); context.setDirty(false); update();
  }
  function switchMode(next) {
    if (busy || next === mode) return;
    reset(); mode = next;
    for (const control of [input, directory, multiple]) control.value = '';
    jsonPanel.hidden = mode !== 'json'; markdownPanel.hidden = mode !== 'markdown';
    for (const [tab, active] of [[jsonTab, mode === 'json'], [markdownTab, mode === 'markdown']]) {
      tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; tab.classList.toggle('active', active);
    }
    chosen.textContent = '尚未选择文件';
  }
  for (const tab of [jsonTab, markdownTab]) tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault(); const markdown = event.key === 'End' || (event.key !== 'Home' && tab === jsonTab);
    switchMode(markdown ? 'markdown' : 'json'); (markdown ? markdownTab : jsonTab).focus();
  });
  async function choose(files, markdown) {
    if (busy || stopped || markdown !== (mode === 'markdown')) return;
    reset(); chosen.textContent = '所选文件尚未准备完成。';
    const current = selection, isCurrent = () => !stopped && current === selection;
    const selected = Array.from(files); if (!selected.length) {chosen.textContent = '尚未选择文件'; return;}
    reading = true; update();
    try {
      if (markdown) {
        const group = markdownSelection(selected);
        chosen.textContent = `已选择 ${group.markdown.length} 个 MD · ${(group.size / 1024).toFixed(1)} KiB；跳过 README ${group.skipped.readme} 个、其他文件 ${group.skipped.other} 个。`;
        const loaded = await readMarkdownSelection(group, {isCurrent, onProgress: (done, total) => {
          if (isCurrent()) chosen.textContent = `正在读取 ${done}/${total} 个 MD；跳过 README ${group.skipped.readme} 个、其他文件 ${group.skipped.other} 个。`;
        }});
        if (!loaded || !isCurrent()) return;
        bytes = loaded.bytes; filename = 'zhihu-markdown'; localReadErrors = loaded.errors;
        chosen.textContent = `可提交 ${loaded.files} 个 MD · 请求 ${((bytes?.byteLength || 0) / 1024).toFixed(1)} KiB；跳过 README ${group.skipped.readme} 个、其他文件 ${group.skipped.other} 个；读取失败 ${loaded.errors.length} 个。`;
        if (loaded.errors.length) localIssues.replaceChildren(notice('以下文件读取失败，未提交；其他有效文件仍可预演和导入。', 'warning'),
          el('ul', {}, ...loaded.errors.map(error => el('li', {}, error.relative_path, '：', error.message))));
      } else {
        const file = selected[0]; chosen.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KiB`;
        if (file.size > MAX_IMPORT_BYTES) throw new Error('文件超过 10 MiB，请拆分后导入。');
        const read = new Uint8Array(await file.arrayBuffer()); if (!isCurrent()) return;
        bytes = read; filename = file.name;
      }
      if (isCurrent()) context.setDirty(Boolean(bytes));
    } catch (error) {if (isCurrent()) showError(error, errors);}
    finally {if (isCurrent()) {reading = false; update();}}
  }
  input.addEventListener('change', () => choose(input.files, false));
  directory.addEventListener('change', () => {if (!busy && mode === 'markdown') {multiple.value = ''; choose(directory.files, true);}});
  multiple.addEventListener('change', () => {if (!busy && mode === 'markdown') {directory.value = ''; choose(multiple.files, true);}});
  async function send(dryRun) {
    if (stopped || busy || reading || !bytes || (!dryRun && !previewed)) return;
    busy = true; previewed = false; update(); errors.replaceChildren();
    const submitted = bytes, current = selection, submittedMode = mode;
    try {
      const endpoint = submittedMode === 'markdown' ? 'zhihu-markdown' : 'zhihu';
      const value = await api(`/api/v1/imports/${endpoint}?dry_run=${dryRun}`, {method: 'POST', rawBody: submitted});
      if (stopped || current !== selection) return;
      report = prepareReport(value, submittedMode); previewed = dryRun;
      if (!dryRun) context.setDirty(false);
      showImportReport(result, report, {markdown: submittedMode === 'markdown', download});
    } catch (error) {
      if (stopped || current !== selection) return;
      if (error.data?.report) {
        report = prepareReport(error.data.report, submittedMode); if (!dryRun) context.setDirty(false);
        showImportReport(result, report, {markdown: submittedMode === 'markdown', download});
      }
      showError(error, errors);
      if (!dryRun) errors.append(notice('未自动重试。若请求中断，先查看资料库，再按需手动预演同一批文件；重复资料不会新增。'));
    } finally {busy = false; if (!stopped) update();}
  }
  function prepareReport(value, submittedMode) {
    const clean = publicImportReport(value);
    if (submittedMode === 'markdown') {
      clean.local_read_failed = localReadErrors.length;
      clean.local_read_errors = localReadErrors.map(error => ({relative_path: error.relative_path, message: error.message}));
    }
    return clean;
  }
  function download() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {type: 'application/json;charset=utf-8'});
    const url = URL.createObjectURL(blob), link = el('a', {href: url, download: `${filename.replace(/\.json$/i, '')}-report.json`});
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  container.append(pageHeading('资料导入', '导入离线知乎资料；保留原文来源，不执行在线抓取。'),
    el('div', {className: 'card stack'}, el('div', {className: 'tabs', role: 'tablist', 'aria-label': '导入格式'}, jsonTab, markdownTab), jsonPanel, markdownPanel, chosen, localIssues,
      notice('提交后导入当前打开的工作台资料库。预演与提交使用同一份已读取内容；重新选择文件或切换模式后，需要重新预演。'),
      el('div', {className: 'page-actions'}, preview, submit), errors), result,
    el('details', {className: 'card'}, el('summary', {}, '查看 JSON 输入协议示例'), el('pre', {className: 'mono'}, JSON.stringify({schema_version: 1, items: [{url: 'https://www.zhihu.com/question/123/answer/456', title: '示例回答', author: '示例作者', content: '已经整理好的原始正文。'}]}, null, 2))));
  return () => {stopped = true; selection++;};
}
