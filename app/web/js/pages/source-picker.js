import {api} from '../api.js';
import {el,button,field,debounce,showError} from '../ui.js';

export async function sourcePicker(initialId = null, {onChange = () => {}, testId = 'knowledge-source'} = {}) {
  const search=el('input',{type:'search',placeholder:'搜索来源标题…','aria-label':'搜索关联来源'});
  const selection=el('select',{'aria-label':'关联来源','data-testid':testId});
  const info=el('small',{className:'muted'}),errors=el('div');
  let selected=initialId,selectedTitle='当前关联来源',offset=0,disposed=false,controller;
  if(initialId)try{const source=await api(`/api/v1/sources/${initialId}?include_deleted=true`);selectedTitle=`${source.title}${source.deleted_at?'（已删除）':''}`;}catch{}
  const previous=button('上一页来源',()=>{offset=Math.max(0,offset-20);load();});
  const more=button('更多来源',()=>{offset+=20;load();});
  const root=el('div',{className:'source-picker'},search,selection,el('div',{className:'page-actions'},previous,more,info),errors);
  async function load(){
    controller?.abort();controller=new AbortController();
    try{
      const page=await api(`/api/v1/ui/sources?${new URLSearchParams({state:'active',q:search.value,offset,limit:20})}`,{signal:controller.signal});if(disposed)return;
      selection.replaceChildren(el('option',{value:''},'无来源 · 独立笔记'));
      if(selected)selection.append(el('option',{value:selected},selectedTitle));
      for(const item of page.items)if(item.id!==selected)selection.append(el('option',{value:item.id},item.title));
      selection.value=selected||'';previous.disabled=offset===0;more.disabled=offset+20>=page.total;info.textContent=`共 ${page.total} 条来源`;
    }catch(error){showError(error,errors);}
  }
  selection.addEventListener('change',()=>{selected=selection.value||null;selectedTitle=selection.selectedOptions[0].textContent;onChange(selected);});
  const delayed=debounce(()=>{offset=0;load();});search.addEventListener('input',delayed);await load();
  return {element:root,value:()=>selected,destroy:()=>{disposed=true;controller?.abort();delayed.cancel();}};
}
