import {api} from '../api.js';
import {el, button, field, select, debounce, showError} from '../ui.js';
import {browseLink, noteCard, unavailable, restore, remember} from './reading-common.js';

export function mountList(root, data, params, alive) {
  let offset = Math.max(0, Number(params.get('offset')) || 0), request = 0, controller, disposed = false;
  const query = el('input', {type:'search', maxLength:2000, value:params.get('q') || '', placeholder:'搜索标题、摘要或原文', 'data-testid':'reading-query'});
  const topic = select([['','全部主题'], ...data.topics.map(x => [x.name, `${x.name} · ${x.count}`])], params.get('topic') || '');
  const category = select([], '');
  const tag = el('input', {value:params.get('tag') || '', maxLength:200, list:'reading-tag-options', placeholder:'选择或输入精确标签'});
  const tagOptions = el('datalist', {id:'reading-tag-options'}, ...data.tags.map(x => el('option', {value:x.name}, `${x.count} 篇`)));
  const month = select([['','全部月份'], ...data.months.map(x => [x,x])], params.get('updated_month') || '');
  const sort = select([['updated_desc','最近更新'],['title_asc','标题顺序']], params.get('sort') || 'updated_desc');
  const heading = el('h1', {}, topic.value || '全部文章');
  root.append(el('header', {className:'reading-page-head'}, el('a', {href:'#/reading'}, '← 阅读总览'), heading,
    el('p', {className:'reading-muted'}, '按已有主题找回收藏，或从原文中的一句话开始检索。')));
  if(data.unavailable_count)root.append(unavailable(data.unavailable_count));
  function categories(selected = '') {
    category.replaceChildren(...[['','全部分类'], ...data.categories.filter(x => !topic.value || x.topic === topic.value).map(x => [x.name, `${x.name} · ${x.count}`])]
      .map(([value,label]) => el('option', {value, selected:value === selected}, label)));
  }
  categories(params.get('category') || '');
  const form = el('form', {className:'reading-filters', role:'search'}, field('关键词',query),
    field('一级主题',topic), field('二级分类',category), field('标签',tag), field('更新月份（北京时间）',month), field('排序',sort),
    tagOptions, button('清除筛选', () => {query.value=topic.value=tag.value=month.value='';sort.value='updated_desc';categories();load(true);}, {className:'reading-clear'}));
  const results = el('div', {'data-testid':'reading-results', 'aria-live':'polite'});
  root.append(form,results);
  function state() {
    return {q:query.value.trim(),topic:topic.value,category:category.value,tag:tag.value.trim(),updated_month:month.value,sort:sort.value,offset};
  }
  let currentHref = browseLink(state());
  const valid = () => !disposed && alive();
  async function load(reset = false, initial = false) {
    if (!valid()) return;
    if (reset) offset = 0;
    const ticket = ++request; controller?.abort(); controller = new AbortController();
    currentHref = browseLink(state()); history.replaceState(null, '', currentHref);
    heading.textContent = topic.value || '全部文章';
    results.setAttribute('aria-busy','true');
    if (!results.children.length) results.append(el('p',{className:'reading-muted'},'正在寻找文章…'));
    try {
      const page = await api('/api/v1/reading/notes?' + new URLSearchParams({...state(),limit:20}), {signal:controller.signal});
      if (!valid() || ticket !== request) return;
      if (offset && offset >= page.total) {offset = Math.max(0, Math.floor((page.total - 1) / 20) * 20); return load(false, initial);}
      results.replaceChildren(el('div', {className:'reading-section-head'}, el('h2', {}, `找到 ${page.total} 篇文章`), el('span', {}, '日期为本地笔记更新时间')));
      for (const note of page.items) results.append(noteCard(note, currentHref, query.value));
      if (!page.items.length) results.append(el('div', {className:'reading-empty'}, el('h3', {}, '没有符合条件的文章'), el('p', {}, '试试更短的关键词，或清除筛选。')));
      if (page.total > 20) results.append(el('nav', {className:'reading-pagination','aria-label':'文章分页'},
        button('上一页',()=>{offset-=20;load();window.scrollTo(0,0);},{disabled:offset===0}),
        el('span', {}, `第 ${Math.floor(offset/20)+1} / ${Math.ceil(page.total/20)} 页`),
        button('下一页',()=>{offset+=20;load();window.scrollTo(0,0);},{disabled:offset+20>=page.total})));
      if (initial) restore(currentHref,valid);
    } catch (error) {if (valid() && ticket === request && error.name !== 'AbortError') showError(error,results);}
    finally {if (ticket === request) results.removeAttribute('aria-busy');}
  }
  const delayed = debounce(()=>load(true),280);
  for (const input of [query,tag]) {
    input.addEventListener('input',event=>{if(!event.isComposing)delayed();});
    input.addEventListener('compositionstart',()=>delayed.cancel());
    input.addEventListener('compositionend',()=>delayed());
  }
  topic.addEventListener('change',()=>{categories();delayed.cancel();load(true);});
  for (const input of [category,month,sort]) input.addEventListener('change',()=>{delayed.cancel();load(true);});
  form.addEventListener('submit',event=>{event.preventDefault();delayed.cancel();load(true);});
  load(false,true);
  return ()=>{remember(currentHref);disposed=true;request++;controller?.abort();delayed.cancel();};
}
