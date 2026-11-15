import {api} from './api.js';
import {el, confirmAction, showError} from './ui.js';
import {installDesktopLifecycle} from './desktop.js';

import {rememberPosition,restorePosition} from './scroll-position.js';
import {primary, routes, sublabels} from './navigation.js';
const modules = Object.fromEntries(routes.map(([key,,file]) => [key, () => import(`./pages/${file}.js`)]));
const main = document.getElementById('main');
document.querySelector('.skip-link').addEventListener('click', event => {event.preventDefault();main.focus();});
const navigation = document.getElementById('navigation');
for (const [path, title, icon] of primary) navigation.append(el('a', {href: `#/${path}`, className: 'nav-link',...(path==='settings'?{'data-testid':'desktop-settings-link'}:{})},
  el('span', {className: 'nav-icon', 'aria-hidden': 'true'}, icon), title));
let stopRestore=()=>{};
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
    stopRestore();rememberPosition(currentHash);
    const returnTo=new URL(hash.slice(1)||'/',location.origin).searchParams.get('return_to');
    if(/^#\//.test(returnTo||''))rememberPosition(returnTo);
    dirty = false; if (cleanup) cleanup(); cleanup = undefined;
    currentHash = hash;
    const url = new URL(hash.slice(1) || '/', location.origin);
    const path = url.pathname.split('/').filter(Boolean);
    const [section = 'reading', id] = path;
    const item = routes.find(([key]) => key === section);
    const owner=section==='organization'&&id==='config'?'settings':item?.[3];
    const crumbs=document.querySelector('.breadcrumb');
    crumbs.replaceChildren(el('a',{href:'#/'+(owner||'reading')},primary.find(x=>x[0]===owner)?.[1]||'阅读书架'));
    if(item&&section===owner&&!id)crumbs.firstElementChild.id='page-title';
    if(item && (section!==owner || id)){crumbs.append(el('span',{},'/'),el('strong',{id:'page-title'},sublabels[id]||item[1]));}
    document.title = `${item?.[1] || '页面不存在'} · Memory OS`;
    [...navigation.querySelectorAll('a'), ...document.querySelectorAll('.settings-link')].forEach(link => {
      const active = link.getAttribute('href') === `#/${owner}`;
      link.classList.toggle('active', active); if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    document.body.classList.remove('nav-open'); toggle.setAttribute('aria-expanded', 'false');
    main.replaceChildren(el('div', {className: 'loading'}, '正在加载…'));
    if (!item) {main.replaceChildren(el('h1', {}, '页面不存在')); return;}
    const module = await modules[section]();
    main.replaceChildren();
    if(section!=='reading')window.scrollTo(0,0);
    cleanup = await module.mount(main, {section, id, path, params: url.searchParams,
      navigate: value => {location.hash = value;}, setDirty: value => {dirty = value;}});
    if(section!=='reading')stopRestore=restorePosition(hash,main);
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
