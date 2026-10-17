import {api} from '../api.js';
import {el,button,field,notice,badge,formatDate,renderMarkdown,confirmAction,showError,pageHeading,toast,debounce} from '../ui.js';
import {sourceSelection} from './source-selection.js';
import {sourceReturn} from './source-navigation.js';

export function mountEditor(container,context) {
  const mountedHash=location.hash,lifecycle={disposed:false,cleanup:null};
  const alive=()=>!lifecycle.disposed&&location.hash===mountedHash;
  initializeEditor(container,context,lifecycle,alive).then(cleanup=>{if(lifecycle.disposed)cleanup?.();else lifecycle.cleanup=cleanup;}).catch(error=>{if(alive())showError(error,container);});
  return()=>{lifecycle.disposed=true;lifecycle.cleanup?.();};
}

async function initializeEditor(container,context,lifecycle,alive) {
  const type=context.section,note=type==='knowledge',isNew=context.id==='new',word=note?'笔记':'资料',base=`/api/v1/${type}`;
  const returnTo=note?null:sourceReturn(context.params.get('return_to'),null);
  function editorRoute(id,values={}){
    const params=new URLSearchParams(values);if(returnTo)params.set('return_to',returnTo);
    return `#/${type}/${id}${params.size?'?'+params:''}`;
  }
  let record=isNew?{title:'',body:'',content:'',summary:'',category:'',tags:[],concepts:[],source_id:null,source_ids:[],source_type:'manual',author:'',url:''}:
    await api(`${base}/${context.id}?include_deleted=true`);
  if(!alive())return;
  const associatedIds=record.source_ids|| (record.source_id?[record.source_id]:[]);
  const errors=el('div'),comparison=el('div'),actions=el('div',{className:'page-actions'}),meta=el('div',{className:'detail-meta'});
  const back=button(`← ${returnTo?.startsWith('#/sources/group')?'返回同标题资料':note?'知识笔记':'资料库'}`,()=>context.navigate(returnTo||`#/${type}`),{'data-testid':'editor-back'});
  container.append(pageHeading(isNew?`新建${word}`:record.title,`在本地保存${note?'自己的理解与思考':'原始信息，保留完整上下文'}。`,back),errors);
  const form=el('form',{className:'card',onSubmit:event=>{event.preventDefault();save();}});
  form.append(el('div',{className:'detail-header'},meta,actions),comparison);
  container.append(form);
  const inputs={};
  function input(name,label,{textarea=false,full=false,...attrs}={}){
    const node=el(textarea?'textarea':'input',{value:record[name]??'',...attrs,'data-testid':`${note?'knowledge':'source'}-${name}`});
    inputs[name]=node;const wrapper=field(label,node);if(full)wrapper.classList.add('full');return wrapper;
  }
  const fields=el('div',{className:'form-grid'});
  fields.append(input('title','标题',{required:true,maxLength:500,full:true,placeholder:`为这篇${word}起个标题`}));
  let picker;
  if(note){
    fields.append(input('summary','摘要',{textarea:true,maxLength:100000,full:true,placeholder:'用几句话概括核心内容（可选）'}));
    fields.append(input('category','分类',{maxLength:200,placeholder:'例如：技术学习'}));
    record.tags=record.tags||[];record.concepts=record.concepts||[];
    fields.append(input('tags','标签',{value:record.tags.join(', '),placeholder:'使用中文或英文逗号分隔'}));
    fields.append(input('concepts','概念',{value:record.concepts.join(', '),placeholder:'例如：索引, B+树'}));
    picker=sourceSelection({initial:associatedIds,onChange:()=>context.setDirty(true),alive,testId:'knowledge',preview:false});
    const association=el('div',{className:'full'},field('关联来源',picker.element,'最多关联 20 篇资料；未选为独立笔记。已删除的原关联仍保留，需主动取消才会解除。'));fields.append(association);
  }else{
    fields.append(input('author','作者',{maxLength:200}));fields.append(input('source_type','来源类型',{required:true,maxLength:50}));
    fields.append(input('url','原文链接',{maxLength:4096,full:true,placeholder:'https://…（可选）'}));
  }
  form.append(fields);
  let updatePreview;
  if(note){
    const source=el('textarea',{className:'editor',value:record.body,maxLength:2000000,'aria-label':'Markdown 正文','data-testid':'knowledge-body'});inputs.body=source;
    const preview=el('div',{className:'preview-pane','data-testid':'markdown-preview'});
    updatePreview=debounce(()=>preview.replaceChildren(renderMarkdown(source.value)),220);source.addEventListener('input',updatePreview);
    preview.replaceChildren(renderMarkdown(source.value));
    form.append(el('div',{className:'editor-toolbar'},el('h3',{},'笔记正文'),el('small',{className:'muted'},'Markdown 源码与安全预览')),
      el('div',{className:'editor-grid'},field('Markdown 源码',source),el('div',{},el('div',{className:'field'},el('label',{},'阅读预览'),preview))));
  }else form.append(input('content','原始正文',{textarea:true,maxLength:2000000,className:'editor',full:true,placeholder:'粘贴或输入需要留存的原始内容。'}));
  const submit=el('button',{type:'submit',className:'btn btn-primary','data-testid':`${note?'knowledge':'source'}-save`},'保存'+word);
  const footer=el('div',{className:'page-actions'},submit);form.append(footer);
  form.addEventListener('input',()=>context.setDirty(true));form.addEventListener('change',()=>context.setDirty(true));
  const initialValues=Object.fromEntries(Object.entries(inputs).map(([key,node])=>[key,node.value]));
  let saving=false;
  let previousControls=[];
  function busy(value){
    if(value===saving)return;
    saving=value;
    if(value){previousControls=[...form.querySelectorAll('input,textarea,select,button')].map(node=>[node,node.disabled]);previousControls.forEach(([node])=>node.disabled=true);}
    else{previousControls.forEach(([node,disabled])=>{if(node.isConnected)node.disabled=disabled;});previousControls=[];}
  }
  function refreshMeta(){
    meta.replaceChildren(...(!isNew?[badge(record.deleted_at?'回收站':`版本 ${record.version}`,record.deleted_at?'warning':'info'),el('span',{},`更新于 ${formatDate(record.updated_at)}`),note?badge(record.sync_status):null].filter(Boolean):[badge('尚未保存')]));
    actions.replaceChildren();
    if(!isNew){
      if(record.deleted_at)actions.append(button('恢复'+word,restore,{'data-testid':'entity-restore'}));
      else actions.append(button('移入回收站',remove,{className:'btn btn-danger','data-testid':'entity-delete'}));
      if(!note)actions.append(button('关联笔记',()=>context.navigate(`#/knowledge?source_id=${record.id}`)),button('生成 AI 草稿',()=>context.navigate(`#/processing?source_id=${record.id}`)));
    }
    submit.disabled=Boolean(record.deleted_at);Object.values(inputs).forEach(node=>node.disabled=Boolean(record.deleted_at));
    if(record.deleted_at&&picker)picker.busy(true);
    if(record.deleted_at)footer.prepend(notice('已删除内容保留在本地，恢复后可继续编辑。','warning'));
  }
  refreshMeta();
  function payload(){
    const values=Object.fromEntries(Object.entries(inputs).map(([key,node])=>[key,node.value]));
    if(note){for(const key of ['tags','concepts'])values[key]=[...new Set(values[key].split(/[,，\n]/).map(s=>s.trim()).filter(Boolean))];values.category=values.category.trim()||null;values.source_ids=picker.ids();}
    else{values.author=values.author.trim()||null;values.url=values.url.trim()||null;}
    return values;
  }
  async function showConflict(error){
    if(!await settleCurrent())return;
    showError(error,errors);if(error.status!==409||isNew)return;
    try{
      const latest=await api(`${base}/${record.id}?include_deleted=true`);
      if(!alive())return;
      comparison.replaceChildren(notice(`当前编辑版本 v${record.version}，服务器版本 v${latest.version}。你的输入仍然保留。请复制需要保留的修改，或载入服务器版本后重新编辑。`,'warning'),
        el('details',{className:'comparison'},el('summary',{},'比较本地输入与服务器版本'),el('div',{className:'split'},
          el('div',{},el('h3',{},'本地未保存输入'),el('pre',{className:'snapshot'},JSON.stringify(payload(),null,2))),
          el('div',{},el('h3',{},'服务器最新版本'),el('pre',{className:'snapshot'},JSON.stringify(latest,null,2))))),
        button('载入服务器版本',async()=>{if(await confirmAction('载入服务器版本将丢弃本地未保存的输入。是否继续？')&&alive()){context.setDirty(false);context.navigate(editorRoute(record.id,{refresh:Date.now()}));}}));
    }catch(error){if(alive())showError(error,errors);}
  }
  async function settleCurrent(){while(!lifecycle.disposed&&!alive())await new Promise(resolve=>setTimeout(resolve,25));return alive();}
  async function save(){
    if(!alive()||saving||record.deleted_at||!form.reportValidity())return;busy(true);errors.replaceChildren();
    try{
      let values=payload();
      if(!isNew){
        values=Object.fromEntries(Object.entries(values).filter(([key])=>key==='source_ids'?JSON.stringify(picker.ids())!==JSON.stringify(associatedIds):inputs[key].value!==initialValues[key]));
        if(!Object.keys(values).length){context.setDirty(false);toast('没有需要保存的修改');if(note)context.navigate('#/');return;}
        values.expected_version=record.version;
      }
      const saved=await api(isNew?base:`${base}/${record.id}`,{method:isNew?'POST':'PATCH',body:values});
      if(!await settleCurrent())return;
      context.setDirty(false);toast(note?`数据库已保存 · Markdown ${saved.sync_status==='synced'?'已同步':'待同步'}`:'资料已保存');
      context.navigate(note?'#/':editorRoute(saved.id,{saved:Date.now()}));
    }catch(error){await showConflict(error);}finally{busy(false);}
  }
  async function remove(){
    if(saving||!await confirmAction(`将这篇${word}移入回收站？内容将保留，之后可以恢复。`)||!alive())return;
    busy(true);try{await api(`${base}/${record.id}?expected_version=${record.version}`,{method:'DELETE'});if(!await settleCurrent())return;context.setDirty(false);toast('已移入回收站');context.navigate(returnTo||`#/${type}?state=deleted`);}catch(error){await showConflict(error);}finally{busy(false);}
  }
  async function restore(){
    if(!alive()||saving)return;busy(true);const body={expected_version:record.version};
    try{
      if(note&&associatedIds.length){
        const sources=await Promise.all(associatedIds.map(id=>api(`/api/v1/sources/${id}?include_deleted=true`)));
        if(!alive())return;
        const deleted=sources.filter(source=>source.deleted_at);
        if(deleted.length){
          const remaining=sources.filter(source=>!source.deleted_at).map(source=>source.id);
          errors.replaceChildren(notice('部分关联来源已删除。请先恢复这些来源，或明确解除已删除的关联后恢复笔记；其他来源会保留。','warning'),
            el('div',{className:'page-actions'},...deleted.map(source=>el('a',{href:`#/sources/${source.id}`},`恢复来源：${source.title}`)),
              button('解除已删除来源并恢复',async()=>{if(saving)return;if(await confirmAction(`解除 ${deleted.length} 个已删除来源关联并恢复笔记？其余 ${remaining.length} 个关联保留。`)&&!saving&&alive())await doRestore({...body,source_ids:remaining});})));
          return;
        }
      }
      await doRestore(body);
    }catch(error){await showConflict(error);}finally{busy(false);}
  }
  async function doRestore(body){
    if(!alive())return;
    busy(true);
    try{await api(`${base}/${record.id}/restore`,{method:'POST',body});if(!await settleCurrent())return;context.setDirty(false);toast(word+'已恢复');context.navigate(editorRoute(record.id,{restored:Date.now()}));}catch(error){await showConflict(error);}finally{busy(false);}
  }
  return()=>{picker?.destroy();updatePreview?.cancel();};
}
