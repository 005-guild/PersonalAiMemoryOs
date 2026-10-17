import {el, button, badge, notice, formatDate, renderMarkdown} from '../ui.js';
import {sourceKind} from './source-navigation.js';

function originalLink(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (['http:', 'https:'].includes(url.protocol)) return el('a', {href: value, target: '_blank', rel: 'noopener noreferrer'}, '打开原文 ↗');
  } catch {}
  return el('span', {className: 'muted'}, '原链接格式不可直接打开');
}

export function sourceCard(record, {index, returnTo, title}) {
  const params = new URLSearchParams({return_to: returnTo});
  const actions = el('div', {className: 'page-actions'},
    el('a', {className: 'btn', href: `#/sources/${record.id}?${params}`, 'data-testid': 'source-group-edit'}, record.deleted_at ? '查看与恢复资料' : '编辑资料'),
    !record.deleted_at && el('a', {className: 'btn', href: `#/processing?${new URLSearchParams({source_id: record.id})}`}, '生成 AI 草稿'),
    el('a', {className: 'btn', href: `#/knowledge?${new URLSearchParams({source_id: record.id})}`}, '关联笔记'), originalLink(record.url));
  const content = record.content || '';
  const reading = el('details', {className: 'source-reading', open: true},
    el('summary', {}, `原始正文 · ${content.length.toLocaleString('zh-CN')} 字符（点击展开 / 收起）`));
  if (record.title !== title) reading.append(notice('此资料的标题已变化。当前显示最新内容，刷新标题列表后可查看新的分组。', 'warning'));
  if (content.length > 100000) {
    const plain = el('div'); let loaded = false;
    const open = button('完整纯文本阅读', () => {
      if (!loaded) {plain.append(el('textarea', {value: content, readOnly: true, className: 'source-plain-reader', 'aria-label': '完整原始正文', 'data-testid': 'source-full-text'})); loaded = true;}
      plain.hidden = false; open.disabled = true;
    });
    reading.append(notice('正文超过 100,000 字符，已暂停 Markdown 预览。可打开完整纯文本阅读；原文没有截断。'), open, plain);
  } else reading.append(content ? renderMarkdown(content) : notice('这篇资料尚未保存正文。'));
  return el('article', {className: 'card source-reading-card', 'data-testid': 'source-group-card', 'data-source-id': record.id},
    el('div', {className: 'detail-header'}, el('h2', {}, `${index}. ${record.author || '未知作者'}`),
      el('div', {className: 'inline-list'}, badge(sourceKind(record)), badge(record.deleted_at ? '已删除' : `v${record.version}`, record.deleted_at ? 'warning' : 'info'))),
    el('p', {className: 'muted'}, `更新于 ${formatDate(record.updated_at)}`), actions, reading);
}
