import {api} from '../api.js';
import {el, button, field, notice, badge, empty, renderMarkdown, formatDate, confirmAction, showError} from '../ui.js';
import {select, pager, details, jsonView, labelStatus, keyValues, dataTable} from './workflow-utils.js';
import {listState} from './list-pagination.js';

function snapshot(title, value, deleted) {
  return el('article', {className: 'card stack'}, el('h3', {}, title), badge(deleted ? '删除状态' : '内容版本'),
    value ? el('div', {className: 'stack'}, el('h4', {}, value.title || '未命名'), el('p', {}, value.summary || ''),
      el('p', {className: 'muted'}, `分类：${value.category || '未分类'} · 标签：${(value.tags || []).join('、')}`),
      renderMarkdown(value.body || ''), details('完整字段快照', jsonView(value))) : notice('该侧未发现可解析的文件内容。请同时检查原始 Markdown 和删除状态。'));
}

export function conflictsPanel(context, {signal, alive = () => true} = {}) {
  const stored = listState('sync-conflicts', {status: 'open'}), state = stored.value;
  let offset = state.offset, size = state.size, selected = context.id || '', sequence = 0, busy = false;
  const list = el('div'), detail = el('div'), errors = el('div');
  const status = select([['open', '待解决'], ['resolved', '已解决'], ['superseded', '已有新冲突'], ['all', '全部冲突']], state.status);
  status.setAttribute('aria-label', '冲突状态');
  status.addEventListener('change', () => load(0));
  async function load(nextOffset = offset, nextSize = size) {
    offset = nextOffset; size = nextSize; Object.assign(state, {offset,size,status:status.value});stored.save();const current = ++sequence;
    try {
      const page = await api(`/api/v1/sync/conflicts?${new URLSearchParams({status: status.value, offset: String(offset), limit: size, summary_only: 'true'})}`, {signal});
      if (!alive() || current !== sequence) return;
      if(offset&&offset>=page.total)return load(Math.max(0,Math.floor((page.total-1)/size)*size));
      const rows = page.items.map(conflict => el('tr', {},
        el('td', {}, el('a', {href: `#/knowledge/${conflict.knowledge_id}`}, conflict.db_snapshot?.title || conflict.knowledge_id), el('div', {className: 'muted'}, conflict.file_path || '路径未知')),
        el('td', {}, conflict.reason, el('div', {}, badge(labelStatus(conflict.status)))), el('td', {}, formatDate(conflict.created_at)),
        el('td', {}, button('查看冲突', () => open(conflict.id), {'data-testid': 'conflict-open'}))));
      list.replaceChildren(rows.length ? dataTable(['笔记 / 路径', '原因 / 状态', '发现时间', '操作'], rows) : empty('没有待处理的冲突', '系统会保留发现的双方版本；正常变更由后台自动同步。'), pager(page, load));
    } catch (error) {if (alive() && current === sequence) showError(error, list);}
  }
  async function open(id) {
    if (busy) return;
    selected = id; errors.replaceChildren();
    try {
      const conflict = await api(`/api/v1/sync/conflicts/${encodeURIComponent(id)}`, {signal});
      if (!alive() || selected !== id) return;
      const database = conflict.db_snapshot;
      const fileDeleted = conflict.file_content == null;
      const chooseDb = button('选择系统版本', () => resolve(conflict, 'database'), {disabled: conflict.status !== 'open', className: 'btn btn-primary', 'data-testid': 'conflict-choose-database'});
      const chooseFile = button('选择 Markdown 版本', () => resolve(conflict, 'markdown'), {disabled: conflict.status !== 'open', 'data-testid': 'conflict-choose-markdown'});
      detail.replaceChildren(el('div', {className: 'stack', 'data-testid': 'conflict-detail'},
        el('div', {className: 'card stack'}, el('h2', {}, '对照并解决冲突'),
          notice('请检查内容与删除状态。选择某侧后，该侧内容或删除状态将作为笔记的最终版本；系统会再次校验双方是否变化。'),
          keyValues([['冲突 ID', conflict.id], ['系统版本', `v${conflict.db_version}`], ['状态', labelStatus(conflict.status)], ['原因', conflict.reason], ['文件路径', conflict.file_path]]),
          el('div', {className: 'page-actions'}, chooseDb, chooseFile, button('重新读取快照', () => open(id))), errors),
        el('div', {className: 'split'}, snapshot('系统数据库版本', database, database?.deleted), snapshot('Markdown 文件版本', conflict.file_snapshot, fileDeleted)),
        el('div', {className: 'card stack'}, details('原始 Markdown（只读）', el('pre', {className: 'text-excerpt'}, conflict.file_content ?? '文件已缺失')), details('上次同步的共同基线', jsonView(conflict.base)))));
    } catch (error) {if (alive()) showError(error, detail);}
  }
  async function resolve(conflict, choice) {
    if (!alive() || busy || conflict.status !== 'open') return;
    const selectedDeleted = choice === 'database' ? conflict.db_snapshot?.deleted : conflict.file_content == null;
    busy = true; let stale = false;
    for (const node of detail.querySelectorAll('button')) node.disabled = true;
    try {
      if (!await confirmAction(`选择${choice === 'database' ? '系统' : 'Markdown'}版本${selectedDeleted ? '将使笔记处于删除状态' : '将用该侧内容完成同步'}。是否继续？`, {title: '解决同步冲突', confirmLabel: '使用所选版本'}) || !alive()) return;
      errors.replaceChildren();
      await api(`/api/v1/sync/conflicts/${conflict.id}/resolve`, {method: 'POST', body: {choice}});
      if (!alive()) return;
      detail.replaceChildren(notice('冲突已解决。文件写入结果可在同步状态中查看。', 'success')); await load(0);
    } catch (error) {
      if (!alive()) return;
      showError(error, errors);
      if (error.status === 409) {
        stale = true;
        errors.append(notice('双方状态已变化，原快照仍保留。本次没有自动覆盖；请刷新冲突列表，重新查看最新双方快照后再选择。', 'warning'), button('刷新冲突列表', () => load(0)));
        await load(0);
      }
    } finally {
      busy = false;
      if (alive()) for (const node of detail.querySelectorAll('button')) {
        node.disabled = stale && Boolean(node.dataset.testid?.startsWith('conflict-choose-'));
      }
    }
  }
  const root = el('section', {className: 'stack'}, el('div', {className: 'card stack'},
    el('div', {className: 'detail-header'}, el('h2', {}, '同步冲突'), el('div', {className: 'page-actions'}, field('筛选', status), button('刷新冲突', () => load(0)))), list), detail);
  const ready = load().then(() => selected ? open(selected) : undefined);
  return {node: root, ready, refresh: () => load()};
}
