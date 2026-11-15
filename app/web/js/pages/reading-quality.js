import {api} from '../api.js';
import {el, button, notice, renderMarkdown, confirmAction} from '../ui.js';

export function summaryReview(root, note, alive, open=false) {
  const panel=el('details',{className:'card stack',open},el('summary',{},'详细摘要与升级')),content=el('div',{className:'stack'});
  panel.append(content);root.append(panel);
  let state,token,busy=false,disposed=false,timer;
  const active=()=>!disposed&&alive();
  async function read(){
    try {
      const [value,control]=await Promise.all([api('/api/v1/collection-organization/quality/'+note.id),api('/api/v1/collection-organization')]);
      if(!active())return;state=value;token=control.csrf_token;
      content.replaceChildren();
      if(value.adopted)content.append(notice('本篇已采用详细摘要。'));
      if(value.previous)content.append(el('details',{},el('summary',{},'采用前的笔记'),renderMarkdown(value.previous.body)));
      if(value.candidate){
        content.append(el('div',{className:'grid'},el('section',{},el('h3',{},'当前笔记'),renderMarkdown(value.current.body)),
          el('section',{},el('h3',{},'候选摘要'),renderMarkdown(value.candidate.markdown))));
        if(value.stale)content.append(notice('原文或笔记版本已变化，请重新生成候选。','warning'));
        else content.append(button('采用这份摘要',()=>perform('adopt')));
      }
      content.append(button('生成详细摘要候选',()=>perform('generate')),el('p',{className:'muted'},
        `${value.estimated_yuan==null?'':`本次保守估计 ¥${value.estimated_yuan.toFixed(2)}。`}与新增整理、主题综述共用每月 ¥${control.config.monthly_budget_yuan}。生成后可对照并采纳。`));
      const job=control.jobs.find(row=>row.mode==='quality'&&['pending','running','paused'].includes(row.status));
      if(job)content.append(notice(`摘要任务${job.status==='paused'?'已暂停，请到收藏整理继续':'处理中，完成后将显示候选'}。`));
      for(const element of content.querySelectorAll('button'))element.disabled=busy||control.read_only||!!job;
    }catch(error){if(active())content.replaceChildren(notice(error.message,'error'));}
  }
  async function perform(action){
    if(busy)return;
    if(action==='generate'&&!await confirmAction(`使用本月剩余额度生成这篇详细摘要候选？${state.estimated_yuan==null?'':`保守估计 ¥${state.estimated_yuan.toFixed(2)}，实际费用按调用记账。`}`,{title:'生成摘要',confirmLabel:'生成'}))return;
    busy=true;
    try {
      const body={expected_version:state.current.version};
      if(action==='adopt')body.candidate_id=state.candidate.id;
      await api(`/api/v1/collection-organization/quality/${note.id}/${action}`,{method:'POST',body,headers:{'X-Configuration-Token':token}});
      if(active()&&action==='adopt'){location.reload();return;}
    }catch(error){if(active())content.prepend(notice(error.message,'error'));}
    finally{busy=false;if(active())await read();}
  }
  read();timer=setInterval(()=>{if(panel.open&&!busy&&!document.hidden)read();},4000);
  return ()=>{disposed=true;clearInterval(timer);};
}
