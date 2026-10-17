import {marked} from '../vendor/marked.js';
import DOMPurify from '../vendor/purify.js';

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'className') node.className = value;
    else if (key in node && !['list','form','style'].includes(key)) node[key] = value;
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function button(label, handler, attrs = {}) {
  return el('button', {type: 'button', className: 'btn', ...attrs, onClick: handler}, label);
}
export function field(label, input, help) {
  if (!input.id) input.id = `field-${crypto.randomUUID()}`;
  return el('div', {className: 'field'}, el('label', {htmlFor: input.id}, label), input,
    help && el('small', {className: 'muted'}, help));
}
export const notice = (text, tone = 'info') => el('div', {className: `notice notice-${tone}`, role: tone === 'error' ? 'alert' : 'status'}, text);
export const badge = (text, tone = '') => el('span', {className: `badge ${tone}`}, text);
export function empty(title = '还没有内容', description = '从创建第一条记录开始。', action) {
  return el('div', {className: 'empty-state'}, el('div', {className: 'empty-symbol', 'aria-hidden': 'true'}, '◇'),
    el('h3', {}, title), el('p', {}, description), action);
}
export const formatDate = value => value ? new Date(value).toLocaleString('zh-CN', {hour12: false}) : '—';
export function showError(error, target) {
  if (error?.name === 'AbortError') return;
  const messages = {409: '记录或状态已变化，请查看最新版本后再操作。', 429: '当前有任务正在处理，请稍后手动操作。', 503: '服务或配置暂不可用，请查看系统状态。', 504: '请求超时；请查看处理记录，勿重复提交。'};
  const node = notice(`${messages[error?.status] || '操作未完成。'} ${error?.message || error}`, 'error');
  if (target) target.replaceChildren(node); else toast(node.textContent, 'error');
  return node;
}
export function toast(text, tone = 'success') {
  const node = notice(text, tone); document.getElementById('toasts').append(node);
  setTimeout(() => node.remove(), 6500);
}
export function confirmAction(message, options = {}) {
  return new Promise(resolve => {
    const dialog = el('dialog', {className: 'confirm-dialog', 'aria-label': options.title || '确认操作'});
    const close = value => {dialog.close(); dialog.remove(); resolve(value);};
    dialog.append(el('h2', {}, options.title || '确认操作'), el('p', {}, message),
      el('div', {className: 'dialog-actions'}, button(options.cancelLabel || '取消', () => close(false)),
        button(options.confirmLabel || '确认', () => close(true), {className: 'btn btn-primary'})));
    dialog.addEventListener('cancel', event => {event.preventDefault(); close(false);});
    document.body.append(dialog); dialog.showModal();
  });
}

const renderer = new marked.Renderer();
renderer.html = () => ''; // Raw HTML is never rendered, including benign tags.
renderer.image = ({text}) => `[图片未加载：${text || '图片'}]`;
export function renderMarkdown(text = '') {
  const node = el('div', {className: 'markdown'});
  if (text.length > 100000) {
    node.append(notice('正文超过 100,000 字符，已暂停预览；源码可完整编辑和保存。')); return node;
  }
  const parsed = marked.parse(text, {renderer, async: false});
  node.append(DOMPurify.sanitize(parsed, {RETURN_DOM_FRAGMENT: true,
    USE_PROFILES: {html: true}, FORBID_TAGS: ['img','style','input','form','iframe','video','audio'],
    FORBID_ATTR: ['style','id','name']}));
  for (const link of node.querySelectorAll('a')) {
    const href = link.getAttribute('href') || '';
    if (!/^(https?:\/\/|mailto:)/i.test(href)) link.removeAttribute('href');
    else {link.target = '_blank'; link.rel = 'noopener noreferrer';}
  }
  return node;
}

export function pageHeading(title, description, ...actions) {
  return el('div', {className: 'page-heading'}, el('div', {}, el('h1', {}, title), el('p', {className: 'muted'}, description)),
    el('div', {className: 'page-actions'}, ...actions));
}
export function select(options, value = '') {
  return el('select', {}, ...options.map(([key, label]) => el('option', {value: key, selected: key === value}, label)));
}
export function debounce(fn, delay = 280) {let timer; const call = (...args) => {clearTimeout(timer); timer = setTimeout(() => fn(...args), delay);}; call.cancel = () => clearTimeout(timer); return call;}
