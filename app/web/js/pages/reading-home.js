import {el} from '../ui.js';
import {browseLink, noteCard, unavailable, restore, remember} from './reading-common.js';

export function mountHome(root, data, alive) {
  const href = '#/reading';
  root.append(el('header', {className:'reading-hero'}, el('div', {className:'reading-eyebrow'}, 'YOUR READING SHELF'),
    el('h1', {}, '收藏之后，慢慢读。'), el('p', {}, `${data.total} 篇文章，${data.topics.length} 个主题。让读过的内容，再次与你相遇。`),
    el('a', {href:browseLink(), className:'reading-primary'}, '检索全部文章 →')));
  if(data.unavailable_count)root.append(unavailable(data.unavailable_count));
  const recent = el('section', {className:'reading-recent'}, el('div', {className:'reading-section-head'},
    el('h2', {}, '最近更新'), el('a', {href:browseLink()}, '查看全部 →')));
  for (const note of data.recent) recent.append(noteCard(note, href));
  if (!data.total) recent.append(el('div', {className:'reading-empty'}, el('h3', {}, '书架等待第一篇文章'),
    el('p', {}, '已经发布并完成导出的知乎收藏会出现在这里。'), el('a', {href:'#/organization'}, '查看收藏整理 →')));
  const topics = el('aside', {className:'reading-topics'}, el('h2', {}, '主题分布'), el('p', {className:'reading-muted'}, '从一个感兴趣的主题开始。'));
  const max = Math.max(1, ...data.topics.map(item => item.count));
  for (const topic of data.topics) topics.append(el('a', {href:browseLink({topic:topic.name}), className:'reading-topic'},
    el('span', {}, topic.name), el('strong', {}, topic.count),
    el('progress', {max, value:topic.count, 'aria-label':`${topic.name}，${topic.count} 篇`} )));
  root.append(el('div', {className:'reading-home-grid'}, recent, topics));
  restore(href, alive);
  return () => remember(href);
}
