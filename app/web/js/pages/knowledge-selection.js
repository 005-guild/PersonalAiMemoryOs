import {api} from '../api.js';
import {el,button,notice,confirmAction,toast} from '../ui.js';
import {localPagination} from './list-pagination.js';

// Selection is deliberately limited to the visible page and its loaded versions.
export function knowledgeSelection({onReload,onBusyChange,isDisposed}) {
  const selected=new Map(),boxes=new Map();
  let items=[],all,busy=false;
  const count=el('span',{role:'status'},'已选择 0 篇'),report=el('div',{'data-testid':'knowledge-bulk-report'});
  const remove=button('批量删除',run,{className:'btn btn-danger',disabled:true,'data-testid':'knowledge-bulk-delete'});
  const clear=button('取消选择',()=>{selected.clear();refresh();},{disabled:true});
  const element=el('div',{className:'selection-bar'},count,remove,clear,
    el('small',{className:'muted'},'仅选择当前页的正常笔记，删除后可从回收站恢复。'));

  function refresh() {
    const eligible=items.filter(item=>!item.deleted_at);
    count.textContent=`已选择 ${selected.size} 篇`;
    remove.disabled=busy||selected.size===0;clear.disabled=busy||selected.size===0;
    for(const [id,box] of boxes){
      box.checked=selected.has(id);box.disabled=busy||!eligible.some(item=>item.id===id);
      box.closest('tr')?.classList.toggle('row-selected',box.checked);
    }
    if(all){
      all.checked=eligible.length>0&&selected.size===eligible.length;
      all.indeterminate=selected.size>0&&selected.size<eligible.length;
      all.disabled=busy||eligible.length===0;
    }
  }
  function setBusy(value){busy=value;refresh();onBusyChange(value);}
  function setItems(value){
    for(const box of boxes.values()){box.disabled=true;box.checked=false;box.closest('tr')?.classList.remove('row-selected');}
    if(all){all.disabled=true;all.checked=false;all.indeterminate=false;}
    selected.clear();boxes.clear();all=undefined;items=value;refresh();
  }
  function header(){
    const box=el('input',{type:'checkbox','aria-label':'全选当前页可删除笔记','data-testid':'knowledge-select-all',onChange:()=>{
      if(busy||box!==all||isDisposed())return;
      selected.clear();if(box.checked)for(const item of items)if(!item.deleted_at)selected.set(item.id,item);
      refresh();
    }});
    all=box;
    refresh();return el('th',{className:'selection-cell',scope:'col'},all);
  }
  function cell(item){
    const box=el('input',{type:'checkbox','aria-label':`选择笔记：${item.title}`,'data-note-id':item.id,
      'data-testid':'knowledge-select',onChange:()=>{
        if(busy||isDisposed()||item.deleted_at||!items.some(value=>value.id===item.id))return;
        if(box.checked)selected.set(item.id,item);else selected.delete(item.id);refresh();
      }});
    boxes.set(item.id,box);refresh();return el('td',{className:'selection-cell'},box);
  }
  async function run(){
    if(busy||!selected.size)return;
    const snapshot=[...selected.values()];let confirmed=false,created=0,failures=[];
    setBusy(true);
    try{
      confirmed=await confirmAction(`将选中的 ${snapshot.length} 篇笔记移入回收站？内容会保留，可在回收站恢复。`,
        {title:'批量删除笔记',confirmLabel:'移入回收站'});
      if(!confirmed||isDisposed())return;
      report.replaceChildren();
      for(let index=0;index<snapshot.length;index++){
        const item=snapshot[index];
        if(isDisposed()){
          failures.push(...snapshot.slice(index).map(value=>({item:value,message:'已离开列表，未提交删除。'})));break;
        }
        try{
          await api(`/api/v1/knowledge/${item.id}?expected_version=${item.version}`,{method:'DELETE'});created++;
        }catch(error){
          const message=error.status===409?'笔记已变化，未删除。请查看最新版本后重新选择。':
            error.status?`删除未完成（${error.status}）：${error.message}`:'连接中断，无法确认删除结果，请刷新列表核对。';
          failures.push({item,message});
          if(!error.status||error.status>=500){
            failures.push(...snapshot.slice(index+1).map(value=>({item:value,message:'因前一请求失败，尚未提交删除。'})));break;
          }
        }
      }
    }finally{setBusy(false);}
    if(!confirmed)return;
    const summary=`已移入回收站 ${created} 篇${failures.length?`，未完成 ${failures.length} 篇`:'。'}`;
    toast(summary,failures.length?'warning':'success');
    if(isDisposed())return;
    report.replaceChildren(notice(summary,failures.length?'warning':'success'));
    if(failures.length)report.append(localPagination(failures, rows=>el('ul',{className:'bulk-failures'},...rows.map(({item,message})=>
      el('li',{},el('a',{href:`#/knowledge/${item.id}`},item.title),'：',message))),{label:'批量删除未完成项分页'}));
    await onReload();
  }
  return {element,report,setItems,header,cell,get busy(){return busy;}};
}
