import {api} from '../api.js';
import {el, button, notice, confirmAction} from '../ui.js';
import {browseLink} from './reading-common.js';

export function mountTopic(root,topic,alive) {
  let disposed=false,busy=false,timer,state,token;
  const active=()=>!disposed&&alive(),content=el('div',{className:'stack'});
  root.append(el('header',{className:'reading-note-head'},el('h1',{},topic),
    el('a',{href:browseLink({topic})},'浏览本主题全部文章 →')),content);
  function points(rows){
    return rows.map(point=>el('section',{},el('h3',{},point.heading),el('p',{},point.text),
      el('ul',{},...point.references.map(reference=>{
        const member=state.members.find(row=>row.knowledge_id===reference.knowledge_id);
        return el('li',{},member?el('a',{href:'#/reading/'+encodeURIComponent(reference.knowledge_id)},member.title):el('span',{},'已移出主题的文章'),
          el('blockquote',{},reference.quote),el('small',{},reference.evidence_id.startsWith('O')?'图片识读依据':'原文依据'));
      }))));
  }
  async function read(){
    try {
      const [value,control]=await Promise.all([api('/api/v1/collection-organization/topics?topic='+encodeURIComponent(topic)),api('/api/v1/collection-organization')]);
      if(!active())return;state=value;token=control.csrf_token;
      content.replaceChildren(el('p',{className:'reading-muted'},`${value.member_count} 篇文章 · 基于单篇摘要与原文依据整理`));
      if(!value.enabled){content.append(notice('主题综述已关闭。'),button('启用主题综述',()=>perform('enable')));return;}
      if(value.stale)content.append(notice('主题成员或文章版本已变化，当前综述待更新。','warning'));
      if(value.result){
        content.append(el('section',{className:'reading-abstract'},el('h2',{},'主题概述'),el('p',{},value.result.overview)),
          ...points(value.result.points));
        if(value.result.disagreements.length)content.append(el('h2',{},'观点差异'),...points(value.result.disagreements));
        content.append(el('section',{},el('h2',{},'条件与局限'),el('p',{},value.result.conditions)));
      }else content.append(notice('点击生成后将在这里显示主题综述。'));
      const generate=button(value.result?'更新主题综述':'生成主题综述',()=>perform('generate'));
      generate.disabled=busy||!!value.pending||topic==='待分类'||control.read_only;
      content.append(generate,el('p',{className:'muted'},`${value.estimated_yuan==null?'':`本次预计约 ¥${value.estimated_yuan.toFixed(2)}，实际费用随结果篇幅变化。`}与收藏整理和质量验收共用每月 ¥${value.monthly_budget_yuan}，超出剩余额度时任务暂停。`),
        button('关闭主题综述',()=>perform('disable')));
      if(value.pending)content.append(notice(value.pending.status==='paused'?'任务已暂停，请到收藏整理查看原因并继续。':'正在整理主题，结果会自动显示。'));
    }catch(error){if(active())content.replaceChildren(notice(error.message,'error'));}
  }
  async function perform(action){
    if(busy)return;
    if(action==='generate'&&!await confirmAction(`使用本月剩余额度生成主题综述？${state.estimated_yuan==null?'':`预计约 ¥${state.estimated_yuan.toFixed(2)}，实际费用随篇幅变化。`}较大的主题会分组处理，每组记录费用。`,{title:'生成主题综述',confirmLabel:'生成'}))return;
    busy=true;
    try {
      await api('/api/v1/collection-organization/topics/'+(action==='generate'?'generate':'config'),{method:'POST',
        headers:{'X-Configuration-Token':token},body:action==='generate'?{topic,expected_fingerprint:state.fingerprint}:{enabled:action==='enable'}});
    }catch(error){if(active())content.prepend(notice(error.message,'error'));}
    finally{busy=false;if(active())await read();}
  }
  read();timer=setInterval(()=>{if(!busy&&!document.hidden)read();},5000);
  return ()=>{disposed=true;clearInterval(timer);};
}
