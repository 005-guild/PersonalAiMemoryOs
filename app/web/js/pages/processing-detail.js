import {api} from '../api.js';
import {el, button, notice, badge, renderMarkdown, formatDate, showError} from '../ui.js';
import {labelStatus, keyValues, jsonView, details} from './workflow-utils.js';

/** Drafts stay immutable; the user edits an ordinary note after adoption. */
export function renderRun(run, context, {onChanged, onRefresh, alive = () => true} = {}) {
  const errors = el('div'); let busy = false;
  const adopted = run.status === 'adopted' && run.adopted_knowledge_id;
  const adopt = button(adopted ? '打开已采纳笔记' : '采纳为新笔记', async () => {
    if (!alive()) return;
    if (adopted) {context.navigate(`#/knowledge/${run.adopted_knowledge_id}`); return;}
    if (busy || adopt.disabled) return; busy = true; let stale = false; adopt.disabled = true; errors.replaceChildren();
    try {
      const value = await api(`/api/v1/processing/runs/${run.id}/adopt`, {method: 'POST', body: {expected_version: run.version}});
      if (!alive()) return;
      context.navigate(`#/knowledge/${value.knowledge.id}`);
      onChanged?.();
    } catch (error) {
      if (!alive()) return;
      showError(error, errors);
      if (error.status === 409) {
        stale = true;
        errors.append(notice('草稿或来源状态已变化。请重新读取草稿，确认最新状态后再决定是否采纳。', 'warning'));
        if (onRefresh) errors.append(button('重新读取草稿', onRefresh));
      }
    }
    finally {busy = false; if (alive()) adopt.disabled = stale;}
  }, {className: 'btn btn-primary', disabled: !adopted && (run.status !== 'ready' || run.source_stale), 'data-testid': 'processing-adopt'});
  const root = el('div', {className: 'stack', 'data-testid': 'processing-run-detail'},
    el('div', {className: 'card stack'},
      el('div', {className: 'detail-header'}, el('div', {}, el('h2', {}, run.result?.title || '处理记录'), badge(labelStatus(run.status))), adopt),
      run.source_stale && notice('来源已修改或删除。这份草稿保留供查看，但不能采纳；请重新选择当前资料主动生成。', 'warning'),
      run.error_code && notice(`生成未完成：${run.error_code}。未创建笔记；系统不会自动重试。`, 'error'),
      keyValues([['运行 ID', run.id], ['模型', `${run.profile_id} · ${run.model}`], ['来源版本', `v${run.source_version}`], ['草稿版本', `v${run.version}`], ['创建时间', formatDate(run.created_at)]]),
      el('a', {href: `#/sources/${run.source_id}`}, '查看原始资料'), errors),
    run.proposal && el('div', {className: 'card stack'},
      el('h2', {}, '笔记预览'), notice('生成与预览不新增笔记；采纳后才能编辑，Markdown 由同步器导出。'),
      el('div', {className: 'page-actions'}, badge(run.proposal.category || '未分类'), ...(run.proposal.tags || []).map(tag => badge(tag))),
      renderMarkdown(run.proposal.body || '')),
    run.result && el('div', {className: 'card stack'}, el('h2', {}, '生成结果'), el('p', {}, run.result.summary),
      el('h3', {}, '核心要点'), el('ul', {}, ...(run.result.key_points || []).map(point => el('li', {}, point))),
      el('h3', {}, '原文观点与 AI 分析'), ...(run.result.opinions?.length ? run.result.opinions.map((opinion, index) => el('article', {className: 'opinion'},
        el('h4', {}, `观点 ${index + 1}`), el('p', {}, opinion.statement), el('blockquote', {}, opinion.evidence), el('p', {className: 'muted'}, 'AI 分析'), el('p', {}, opinion.analysis))) : [el('p', {className: 'muted'}, '未提取到明确的原文观点。')])),
    el('div', {className: 'card stack'}, details('来源快照', jsonView(run.source_snapshot)), details('用量与处理元数据', jsonView({usage: run.usage, protocol: run.protocol, prompt_version: run.prompt_version, config_fingerprint: run.config_fingerprint}))));
  return root;
}
