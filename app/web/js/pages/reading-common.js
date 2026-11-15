import {el} from '../ui.js';

const positions = new Map();
export const localDate = value => new Date(value).toLocaleDateString('zh-CN', {timeZone:'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit'});
export function browseLink(values = {}) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {if (value !== '' && value !== null && value !== undefined) params.set(key, String(value));});
  return '#/reading/browse' + (params.size ? '?' + params : '');
}
export function safeReturn(value) {
  return /^#\/(?:reading(?:\/browse)?|search)(?:\?[^#]*)?$/.test(value || '') ? value : '#/reading/browse';
}
export function remember(href) {
  positions.delete(href); positions.set(href, window.scrollY);
  if (positions.size > 50) positions.delete(positions.keys().next().value);
}
export function restore(href, alive) {
  requestAnimationFrame(() => {if (alive()) window.scrollTo(0, positions.get(href) || 0);});
}
export function highlighted(value, query = '') {
  const text = String(value || ''), needle = query.trim().toLocaleLowerCase();
  const fragment = document.createDocumentFragment();
  if (!needle) {fragment.append(text); return fragment;}
  const folded = text.toLocaleLowerCase(); let start = 0, index;
  while ((index = folded.indexOf(needle, start)) >= 0) {
    fragment.append(text.slice(start, index), el('mark', {}, text.slice(index, index + needle.length)));
    start = index + needle.length;
  }
  fragment.append(text.slice(start)); return fragment;
}
export function noteCard(note, from, query = '') {
  const href = `#/reading/${note.knowledge_id}?${new URLSearchParams({from})}`;
  const heading = el('a', {href, className:'reading-note-link', onClick:() => remember(from)}, highlighted(note.title, query));
  const card = el('article', {className:'reading-card', 'data-testid':'reading-card'},
    el('div', {className:'reading-kicker'}, note.category, el('span', {}, '更新于 ' + localDate(note.updated_at))),
    el('h2', {}, heading), el('p', {className:'reading-summary'}, highlighted(note.summary, query)),
    el('div', {className:'reading-card-meta'}, el('span', {}, note.author || (note.source_kind==='other'?'知识笔记':'作者未注明')),
      el('span', {className:'reading-tags'}, note.tags.slice(0, 6).join(' · ')),el('span',{},note.source_kind==='other'?'普通笔记':'知乎收藏')));
  if (query && note.excerpt) card.append(el('p', {className:'reading-excerpt'},
    el('span', {className:'reading-match-label'}, ({title:'标题命中', summary:'摘要命中', tag:'标签命中', original:'原文 / 正文命中'})[note.match_section] + ' '),
    highlighted(note.excerpt, query)));
  return card;
}
export function unavailable(count) {
  return count ? el('p', {className:'reading-status', role:'status'}, `${count} 篇文章待同步或需处理。`,
    el('a', {href:'#/organization'}, '前往收藏整理 →')) : null;
}
