import {api} from '../api.js';
import {el, showError} from '../ui.js';
import {mountHome} from './reading-home.js';
import {mountList} from './reading-list.js';
import {mountNote} from './reading-note.js';
import {mountTopic} from './reading-topic.js';

export function mount(container, context) {
  const root = el('div', {className:'reading-root'});
  container.append(root);
  const controller = new AbortController(); let disposed = false, cleanup;
  const alive = () => !disposed && root.isConnected;
  root.append(el('nav', {className:'reading-nav','aria-label':'阅读导航'},
    el('a', {href:'#/reading', className:!context.id?'active':''}, '阅读总览'),
    el('a', {href:'#/reading/browse', className:context.id==='browse'?'active':''}, '全部文章'),
    el('a', {href:'#/search'}, '搜索问答 ↗')));
  const content = el('div', {}, el('p', {className:'reading-muted'}, '正在打开书架…')); root.append(content);
  async function start() {
    try {
      if(context.id==='topic'){
        content.replaceChildren();cleanup=mountTopic(content,context.params.get('name')||'',alive);return;
      }
      if (context.id && context.id !== 'browse') {
        const data = await api('/api/v1/reading/notes/' + encodeURIComponent(context.id), {signal:controller.signal});
        if (!alive()) return;
        content.replaceChildren(); cleanup = mountNote(content,data,context.params,alive);
      } else {
        const data = await api('/api/v1/reading/overview', {signal:controller.signal});
        if (!alive()) return;
        content.replaceChildren(); cleanup = context.id ? mountList(content,data,context.params,alive) : mountHome(content,data,alive);
      }
    } catch (error) {
      if (!alive() || error.name==='AbortError') return;
      if ([404,409].includes(error.status)) content.replaceChildren(el('div', {className:'reading-empty'},
        el('h1', {}, error.status===404?'这篇文章已不在书架':'这篇文章暂时无法阅读'),
        el('p', {}, '文章可能已删除、正在同步，或需要处理整理冲突。'),
        el('a', {href:'#/organization'}, '前往收藏整理 →'), el('a', {href:'#/reading'}, ' 返回阅读总览')));
      else showError(error,content);
    }
  }
  start();
  return ()=>{disposed=true;controller.abort();cleanup?.();};
}
