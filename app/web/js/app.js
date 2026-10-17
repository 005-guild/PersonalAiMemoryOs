import {api} from './api.js';
import {el, confirmAction, showError} from './ui.js';
import {installDesktopLifecycle} from './desktop.js';

const routes = [
  ['', '概览', '◫', 'overview'], ['sources', '资料库', '▤', 'content'],
  ['imports', '资料导入', '↥', 'imports'], ['knowledge', '知识笔记', '▧', 'content'],
  ['processing', 'AI 草稿', '✧', 'processing'], ['search', '搜索问答', '⌕', 'search'],
  ['system', '同步与系统', '⚙', 'system'], ['settings', '设置', '⚙', 'settings'],
];
const modules = Object.fromEntries(routes.map(([key,,,file]) => [key, () => import(`./pages/${file}.js`)]));
const main = document.getElementById('main');
document.querySelector('.skip-link').addEventListener('click', event => {event.preventDefault();main.focus();});
const navigation = document.getElementById('navigation');
for (const [path, title, icon] of routes.filter(([path]) => path !== 'settings')) navigation.append(el('a', {href: `#/${path}`, className: 'nav-link'},
  el('span', {className: 'nav-icon', 'aria-hidden': 'true'}, icon), title));
let dirty = false, cleanup, currentHash = '', routing = false, pendingHash;
installDesktopLifecycle(() => dirty, () => {dirty = false;});
window.addEventListener('beforeunload', event => {if (dirty) {event.preventDefault(); event.returnValue = '';}});
const toggle = document.getElementById('menu-toggle');
toggle.addEventListener('click', () => {const open = document.body.classList.toggle('nav-open'); toggle.setAttribute('aria-expanded', String(open));});
async function route() {
  if (routing) {pendingHash = location.hash; return;}
  routing = true;
  const hash = location.hash || '#/';
  try {
    if (dirty && !await confirmAction('有未保存的修改。离开后将丢失这些修改，是否继续？', {title: '离开编辑页面', confirmLabel: '离开'})) {
      history.replaceState(null, '', currentHash); return;
    }
    dirty = false; if (cleanup) cleanup(); cleanup = undefined;
    currentHash = hash;
    const url = new URL(hash.slice(1) || '/', location.origin);
    const [section = '', id] = url.pathname.split('/').filter(Boolean);
    const item = routes.find(([key]) => key === section);
    document.getElementById('page-title').textContent = item?.[1] || '页面不存在';
    document.title = `${item?.[1] || '页面不存在'} · Memory OS`;
    [...navigation.querySelectorAll('a'), ...document.querySelectorAll('.settings-link')].forEach(link => {
      const active = link.getAttribute('href') === `#/${section}`;
      link.classList.toggle('active', active); if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    document.body.classList.remove('nav-open'); toggle.setAttribute('aria-expanded', 'false');
    main.replaceChildren(el('div', {className: 'loading'}, '正在加载…'));
    if (!item) {main.replaceChildren(el('h1', {}, '页面不存在')); return;}
    const module = await modules[section]();
    main.replaceChildren();
    cleanup = await module.mount(main, {section, id, params: url.searchParams,
      navigate: value => {location.hash = value;}, setDirty: value => {dirty = value;}});
    main.focus({preventScroll: true});
  } catch (error) {showError(error, main);}
  finally {routing = false; if (pendingHash && pendingHash !== currentHash) {pendingHash = null; route();}}
}
window.addEventListener('hashchange', route);
async function health() {
  if (document.hidden) return;
  const node = document.getElementById('service-status');
  try {await api('/health'); node.textContent = '服务已连接'; node.className = 'service-status online';}
  catch {node.textContent = '服务连接中断'; node.className = 'service-status offline';}
}
health(); setInterval(health, 15000); route();
