import {api} from '../api.js';
import {el,button,field,notice,badge,empty,formatDate,renderMarkdown,confirmAction,showError,pageHeading,select,debounce,toast} from '../ui.js';
import {mountEditor} from './editor.js';
import {knowledgeSelection} from './knowledge-selection.js';
import {mountSources} from './sources.js';
import {mountSourceGroup} from './source-group.js';

export async function mount(container,context) {
  const type = context.section, note = type === 'knowledge', label = note ? '知识笔记' : '原始资料';
  if (!note) {
    if (context.id === 'group') return mountSourceGroup(container, context);
    if (!context.id) return mountSources(container, context);
  }
  if (context.id) return mountEditor(container,context);
  container.append(pageHeading(label,note ? '把信息整理成可以反复使用的知识。' : '收集原始内容，保留知识的来处。',
    button(`＋ 新建${note?'笔记':'资料'}`,()=>context.navigate(`#/${type}/new`),{className:'btn btn-primary'})));
  const card=el('section',{className:'card'}), search=el('input',{type:'search',placeholder:'按标题搜索…','aria-label':'标题筛选'}),
    state=select([['active','正常'],['deleted','回收站'],['all','全部']],context.params.get('state') || 'active');
  state.setAttribute('aria-label','记录状态');
  const toolbar=el('div',{className:'toolbar'},search,state);
  let sourceId=context.params.get('source_id') || '';
  if (note) {
    const sourceFilter=el('input',{placeholder:'按来源 UUID 筛选',value:sourceId,'aria-label':'来源筛选'});
    sourceFilter.addEventListener('change',()=>{sourceId=sourceFilter.value.trim();offset=0;load();});toolbar.append(sourceFilter);
  }
  const results=el('div'),errorBox=el('div');
  let offset=0,controller,disposed=false,previousControls=[];
  const selection=note?knowledgeSelection({onReload:load,isDisposed:()=>disposed,onBusyChange:value=>{
    if(value){previousControls=[...card.querySelectorAll('.toolbar input,.toolbar select,.pagination button')].map(control=>[control,control.disabled]);previousControls.forEach(([control])=>control.disabled=true);}
    else{previousControls.forEach(([control,disabled])=>{if(control.isConnected)control.disabled=disabled;});previousControls=[];}
  }}):null;
  card.append(toolbar,...(selection?[selection.element,selection.report]:[]),errorBox,results);container.append(card);
  async function load() {
    if(selection?.busy)return;
    controller?.abort();controller=new AbortController();errorBox.replaceChildren();selection?.setItems([]);
    const query=new URLSearchParams({q:search.value,state:state.value,offset,limit:20});if(sourceId)query.set('source_id',sourceId);
    try {
      const page=await api(`/api/v1/ui/${type}?${query}`,{signal:controller.signal});if(disposed)return;
      if(offset>0&&offset>=page.total){offset=Math.max(0,Math.floor((page.total-1)/20)*20);return load();}
      selection?.setItems(page.items);
      results.replaceChildren();
      if (!page.items.length) results.append(empty(state.value==='deleted'?'回收站为空':'还没有匹配的记录',search.value?'换一个关键词试试。':`新建一条${note?'笔记':'资料'}，开始建立知识库。`));
      else {
        const heading=el('thead',{},el('tr',{},selection?.header(),el('th',{},'标题'),el('th',{},note?'分类 / 同步':'来源类型'),el('th',{className:'hide-mobile'},'更新于'),el('th',{},'状态')));
        const rows=page.items.map(item=>el('tr',{},
          selection?.cell(item),
          el('td',{},el('a',{href:`#/${type}/${item.id}`,className:'record-title'},item.title),el('span',{className:'record-excerpt'},note?item.summary:item.excerpt)),
          el('td',{},note?el('div',{},badge(item.category||'未分类'),el('small',{className:'status-detail'},item.sync_status)):badge(item.source_type)),
          el('td',{className:'hide-mobile'},formatDate(item.updated_at)),
          el('td',{},badge(item.deleted_at?'已删除':`v${item.version}`,item.deleted_at?'':'info'))));
        results.append(el('div',{className:'table-wrap'},el('table',{className:'data-table'},heading,el('tbody',{},...rows))));
      }
      results.append(el('div',{className:'pagination'},el('span',{},`共 ${page.total} 条 · 第 ${Math.floor(offset/20)+1} 页`),
        el('div',{className:'pagination-controls'},button('上一页',()=>{offset=Math.max(0,offset-20);load();},{disabled:offset===0}),button('下一页',()=>{offset+=20;load();},{disabled:offset+20>=page.total}))));
    } catch(error){showError(error,errorBox);}
  }
  const delayed=debounce(()=>{offset=0;load();});search.addEventListener('input',()=>{selection?.setItems([]);delayed();});state.addEventListener('change',()=>{offset=0;load();});
  await load();return()=>{disposed=true;controller?.abort();delayed.cancel();};
}
