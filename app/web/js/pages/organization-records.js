import {api} from '../api.js';
import {el,button,pageHeading,notice,renderMarkdown,showError,confirmAction} from '../ui.js';
import {remoteList} from './remote-list.js';
import {partialImageReview} from './organization-review.js';
import {backLink} from './workspace-common.js';

const endpoint='/api/v1/collection-organization';
export function mountRecords(container,context){
  let disposed=false,busy=false,control;const controller=new AbortController(),alive=()=>!disposed;
  const messages=el('div'),body=el('div',{className:'stack'});
  const mode=context.id,item=context.params.get('item'),job=context.params.get('job');
  const current=location.hash;
  container.append(backLink('#/organization','收藏整理'),pageHeading(mode==='jobs'?'任务记录':mode==='review'?'样本审核':'处理记录','列表查看状态，点击进入完整内容。'),messages,body);
  async function action(name,payload={}){
    if(busy||!control||control.read_only)return;
    if(name.includes('retry')&&!await confirmAction('显式重试可能再次产生费用。是否继续？',{confirmLabel:'重试'}))return;
    busy=true;
    try{await api(endpoint+'/'+name,{method:'POST',body:payload,headers:{'X-Configuration-Token':control.csrf_token}});if(alive()){messages.replaceChildren(notice('操作已提交。'));await load();}}
    catch(error){if(alive())showError(error,messages);}finally{busy=false;}
  }
  async function load(){try{
    control=await api(endpoint,{signal:controller.signal});if(!alive())return;
    body.replaceChildren();
    if(item){
      const value=await api(endpoint+'/records/'+encodeURIComponent(item),{signal:controller.signal});if(!alive())return;
      const result=value.result;
      body.append(el('h2',{},result?.title||value.title),el('p',{},value.status+(value.error?' · '+value.error:'')));
      if(result)body.append(el('section',{className:'card stack'},el('h3',{},'整理结果'),el('p',{},result.category+' · '+result.tags.join(' / ')),el('p',{},result.summary),el('ul',{},...result.points.map(p=>el('li',{},p))),el('p',{},result.conditions||''),...(result.quotes||[]).map(q=>el('blockquote',{},q))));
      body.append(el('details',{className:'card'},el('summary',{},'对照原文'),renderMarkdown(value.original.content)));
      if(value.knowledge_id)body.append(el('a',{href:'#/reading/'+value.knowledge_id},'阅读已入库笔记 →'));
      if(value.error==='image_needs_review'){
        const review=partialImageReview(v=>action('items/'+v.id+'/approve-partial-image',{input_hash:v.input_hash}));review.render([value],control.read_only);body.append(review.element);
      }
      const params=new URLSearchParams(context.params);params.delete('item');params.delete('position');
      body.append(backLink('#/organization/'+mode+'?'+params,'返回记录列表'));
      const position=Number(context.params.get('position'))||0;
      const filter=mode==='review'?{job_id:control.sample_job_id}:Object.fromEntries(['status','error','job_id'].map(k=>[k,context.params.get(k)||'']));
      const adjacent=el('div',{className:'page-actions'});body.append(adjacent);
      for(const [next,label] of [[position-1,'上一篇'],[position+1,'下一篇']]){
        if(next<0)continue;
        const page=await api(endpoint+'/records?'+new URLSearchParams({...filter,offset:next,limit:1}),{signal:controller.signal});if(!alive())return;
        if(page.items.length)adjacent.append(el('a',{className:'btn',href:'#/organization/'+mode+'?'+new URLSearchParams({...Object.fromEntries(params),item:page.items[0].id,position:next})},label));
      }
    }else if(mode==='jobs'&&job){
      const value=await api(endpoint+'/jobs/'+job,{signal:controller.signal});if(!alive())return;
      body.append(el('section',{className:'card stack'},el('h2',{},value.mode+' · '+value.status),el('p',{},value.count+' 篇'),value.error&&notice(value.error,'warning')));
      if(['paused','failed'].includes(value.status)&&['quality','topic'].includes(value.mode))body.append(button('显式重试此任务',()=>action('jobs/'+job+'/retry')));
      else if(value.status==='paused')body.append(button('复用响应继续',()=>action('resume',{job_id:job})),button('结束暂停任务',()=>action('cancel',{job_id:job})));
      records({job_id:job});
    }else if(mode==='jobs'){
      const list=remoteList(endpoint+'/jobs',rows=>el('div',{},...rows.map(v=>el('a',{className:'status-row',href:'#/organization/jobs?job='+v.id},v.mode+' · '+v.status+' · '+v.count+' 篇'))),{label:'任务分页',alive,signal:controller.signal});body.append(list.element);
    }else{
      if(mode==='review'){
        if(!control.sample_job_id){body.append(notice('尚未生成样本，请返回收藏整理生成。'));return;}
        const sample=control.jobs.find(j=>j.id===control.sample_job_id);
        body.append(notice(control.approved?'当前样本样式已确认。':'逐篇检查标题、分类、摘要和原文依据。'));
        if(!control.approved&&sample?.status==='completed')body.append(button('确认这批样本',()=>action('approve',{job_id:control.sample_job_id})));
        if(['paused','failed','completed_with_errors'].includes(sample?.status))body.append(button('复用响应继续样本',()=>action('continue-sample',{job_id:control.sample_job_id})),button('手动重试失败样本',()=>action('retry-sample',{job_id:control.sample_job_id})));
      }
      records(mode==='review'?{job_id:control.sample_job_id}:Object.fromEntries(['status','error','job_id'].map(k=>[k,context.params.get(k)||''])));
    }
  }catch(error){if(alive()&&error.name!=='AbortError')showError(error,messages);}}
  function records(params){
    const list=remoteList(endpoint+'/records',(rows,offset)=>el('div',{},...rows.map((v,index)=>el('a',{className:'status-row',href:'#/organization/'+(mode==='jobs'?'records':mode)+'?'+new URLSearchParams({...params,item:v.id,offset,position:offset+index})},el('span',{},v.title),el('small',{},v.status+(v.error?' · '+v.error:''))))),{label:'处理记录分页',key:current,params,alive,signal:controller.signal});body.append(list.element);
  }
  container.append(button('刷新状态',load));
  load();return()=>{disposed=true;controller.abort();};
}
