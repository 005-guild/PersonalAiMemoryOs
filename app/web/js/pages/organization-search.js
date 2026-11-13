import {api} from '../api.js';
import {el, button, field, notice, select, showError} from '../ui.js';

export function collectionSearch(alive) {
  let busy = false, offset = 0;
  const q = el('input', {placeholder:'输入关键词或用一句话描述你想找的内容', maxLength:2000});
  const mode = select([['keyword','关键词（本地全文）'],['semantic','语义（本地向量）']]);
  const category = el('input', {placeholder:'例如：技术/人工智能', maxLength:80});
  const tag = el('input', {placeholder:'精确标签，可留空', maxLength:80});
  const results = el('div', {className:'stack', 'aria-live':'polite'});
  async function search(reset = true) {
    if (busy) return;
    if (reset) offset = 0;
    busy = true; submit.disabled = true;
    try {
      const params = new URLSearchParams({q:q.value.trim(),mode:mode.value,category:category.value.trim(),tag:tag.value.trim(),offset,limit:20});
      const data = await api('/api/v1/collection-organization/search?'+params);
      if (!alive()) return;
      results.replaceChildren(el('p', {className:'muted'}, `找到 ${data.total} 篇${data.index_incomplete ? ' · 向量索引尚未全部就绪' : ''}`));
      for (const item of data.items) results.append(el('article', {className:'card stack'},
        el('h3', {}, el('a', {href:'#/knowledge/'+item.knowledge_id}, item.title)),
        el('p', {className:'muted'}, item.category+' · '+item.tags.join(' / ')),
        el('p', {}, item.excerpt), el('small', {}, `匹配：${({summary:'标题 / 摘要',original:'原文',semantic:'语义'})[item.match_section]}`),
        el('a', {href:item.source_url,target:'_blank',rel:'noopener noreferrer'}, '原文：'+item.source_title)));
      if (mode.value==='keyword') results.append(el('div', {className:'page-actions'},
        button('上一页',()=>{offset=Math.max(0,offset-20);search(false);},{disabled:offset===0}),
        button('下一页',()=>{offset+=20;search(false);},{disabled:offset+20>=data.total})));
    } catch (error) {if (alive()) showError(error,results);}
    finally {busy=false;submit.disabled=false;}
  }
  const submit = button('检索',()=>search(),{className:'btn btn-primary'});
  q.addEventListener('keydown',event=>{if(event.key==='Enter')search();});
  return el('section',{className:'card stack'},el('h2',{},'快速检索'),
    notice('搜索已整理的标题、摘要和完整原文。关键词查询离线可用；语义检索需要本地向量服务。检索本身不调用 DeepSeek。'),
    field('查询内容',q),el('div',{className:'form-grid'},field('检索方式',mode),field('分类筛选',category),field('标签筛选',tag)),submit,results);
}
