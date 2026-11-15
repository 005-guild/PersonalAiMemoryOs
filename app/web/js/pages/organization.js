import {api} from '../api.js';
import {el,button,field,notice,pageHeading} from '../ui.js';
import {mountRecords} from './organization-records.js';
import {entryGrid,backLink} from './workspace-common.js';

const endpoint='/api/v1/collection-organization';
const labels={discovered:'待整理',ready:'摘要已生成',published:'已入库',failed:'失败',pending:'等待执行',running:'执行中',paused:'已暂停',completed:'完成',completed_with_errors:'部分失败'};
const errors={sample_approval_required:'请先查看并确认样本。',sample_not_ready:'样本尚未全部完成。',
  organization_busy:'已有任务执行中。',paused_job_exists:'请先继续已暂停的任务。',configuration_changed:'配置已变化，请刷新后重试。',
  configuration_incomplete:'请先保存输入和输出目录。',organization_paths_locked:'已有整理记录，不能直接更换目录。',
  organization_budget_exhausted:'本期预算不足，已暂停。可调高预算后继续；跨月任务继续时按当月预算检查。',
  organization_upstream_unavailable:'上游连续 3 次请求失败，任务已暂停。检查网络和模型服务后继续；失败请求不会自动重试。',
  explicit_retry_required:'上次模型请求结果不确定或校验失败，未自动重试。',organization_output_invalid:'模型结果未通过格式或原文依据校验。',
  image_needs_review:'图片内容不够清晰，需要人工检查。',source_changed:'原文或图片已变化，已停止该条整理。',
  image_invalid:'图片文件无法解码，请检查原图。',image_too_large:'图片超出本地安全处理上限，请检查原图。',
  image_review_changed:'文章或审核状态已变化，请重新查看后再确认。',
  export_conflict:'整理文件被外部修改，已保留修改；请核对后恢复原导出文件，再手动重试。',
  organization_profile_unsupported:'请选择官方 DeepSeek deepseek-flash / Chat 或 OpenAI GPT-6.1 Sol / Responses 配置。',
  organization_profile_changed:'模型配置已变化，请核对并使用“切换模型并保留样式确认”。',
  organization_token_count_failed:'输入费用计数失败，未发起生成请求。',invalid_token_count:'输入费用计数无效，未发起生成请求。',
  organization_configuration_invalid:'请检查 AI 配置、模型、密钥和目录。',configuration_read_only:'当前实例为只读模式。'};
const explain=code=>errors[code]||code;

export async function mount(container,context) {
  if(['records','review','jobs'].includes(context.id))return mountRecords(container,context);
  const configPage=context.id==='config';
  let alive=true,dirty=false,busy=false,state,timer;
  const messages=el('div'),status=el('div');
  const changed=()=>{dirty=true;context.setDirty(true);};
  const input=el('input',{onInput:changed,placeholder:'articles 文件夹绝对路径'});
  const output=el('input',{onInput:changed,placeholder:'整理库文件夹绝对路径'});
  const profile=el('input',{onInput:changed});
  const initial=el('input',{type:'number',min:1,max:10000,onInput:changed});
  const monthly=el('input',{type:'number',min:1,max:10000,onInput:changed});
  const enabled=el('input',{type:'checkbox',onChange:changed});
  const taxonomy=el('textarea',{rows:8,onInput:changed,placeholder:'首次留空，模型会根据收藏主题提出分类。每行一个“一级/二级”。'});
  const fields=[input,output,profile,initial,monthly,enabled,taxonomy],controls=[];
  function error(error){messages.replaceChildren(notice(explain(error.detail?.code||error.message),'error'));}
  async function read(fill=false){
    const value=await api(endpoint);if(!alive)return;
    state=value;
    if(fill){const c=value.config;input.value=c.input_dir;output.value=c.output_dir;profile.value=c.profile_id;
      initial.value=c.initial_budget_yuan;monthly.value=c.monthly_budget_yuan;enabled.checked=c.enabled;taxonomy.value=c.taxonomy.join('\n');
      dirty=false;context.setDirty(false);}
    else if(!dirty)taxonomy.value=value.config.taxonomy.join('\n');
    const running=value.jobs.find(j=>['running','pending','paused'].includes(j.status));
    status.replaceChildren(el('p',{},Object.entries(value.counts).map(([key,n])=>`${labels[key]||key} ${n}`).join(' · ')||'尚未扫描收藏'),
      el('p',{},`样本：${value.approved?'已确认':'待确认'} · 自动整理：${value.config.enabled?'开启':'关闭'}${value.paused?' · 已暂停':''}`),
      ...value.budgets.map(b=>el('p',{className:'muted'},`${b.period==='initial'?'首次整理':b.period}：已记账 / 预留 ¥${b.accounted_yuan.toFixed(4)} · ${b.calls} 次请求`)));
    if(running)status.append(notice(`${labels[running.status]}：${running.selection.length} 篇${running.error?' · '+explain(running.error):''}`));
    if(value.last_error)status.append(notice(explain(value.last_error),'warning'));
    for(const job of value.jobs.filter(row=>['quality','topic'].includes(row.mode)&&['failed','paused'].includes(row.status)).slice(0,3)){
      status.append(el('a',{href:'#/organization/jobs?job='+job.id},`${job.mode==='topic'?'主题综述':'详细摘要'} · ${labels[job.status]} · 查看与处理 →`));
    }
    for(const f of fields)f.disabled=busy||value.read_only;
    for(const c of controls)c.disabled=busy||value.read_only;
    approve.disabled=busy||value.read_only||value.approved||!value.jobs.some(j=>j.id===value.sample_job_id&&j.status==='completed');
    all.disabled=busy||value.read_only||!value.approved;
    resume.disabled=busy||value.read_only||!value.paused;
    for(const c of controls){
      const action=c.dataset.action;
      if(!configPage)c.hidden=action==='sample'?value.approved:action==='all'?!value.approved:
        ['resume','cancel'].includes(action)?!value.paused:['continue','retry'].includes(action)?!value.counts.failed:
        action==='pause'?!value.config.enabled&&!running:false;
    }
  }
  async function perform(action){
    if(busy||!state)return;
    if(dirty&&!['save','pause','switch-profile'].includes(action)){messages.replaceChildren(notice('请先保存设置。','warning'));return;}
    if(action==='save'&&!fields.every(x=>x.reportValidity()))return;
    const selected=state.available_profiles?.find(x=>x.id===profile.value.trim());
    if(action==='switch-profile'){
      const c=state.config;
      if(!selected){messages.replaceChildren(notice('请先在模型设置中启用并配置目标模型，然后重启应用。','warning'));return;}
      if(input.value.trim()!==c.input_dir||output.value.trim()!==c.output_dir||Number(initial.value)!==c.initial_budget_yuan||
          Number(monthly.value)!==c.monthly_budget_yuan||enabled.checked!==c.enabled||taxonomy.value.split('\n').map(x=>x.trim()).filter(Boolean).join('\n')!==c.taxonomy.join('\n')){
        messages.replaceChildren(notice('切换模型仅修改模型选择。请先使用原模型名称保存其他设置，再切换模型。','warning'));return;}
    }
    busy=true;messages.replaceChildren();
    for(const element of [...controls,...fields])element.disabled=true;
    try{
      const job_id=['resume','cancel'].includes(action)?state.jobs.find(j=>j.status==='paused')?.id:state.sample_job_id;
      const body=action==='switch-profile'?{profile_id:selected.id,expected_revision:state.revision,expected_profile_fingerprint:selected.fingerprint}:
        action==='save'?{input_dir:input.value.trim(),output_dir:output.value.trim(),profile_id:profile.value.trim(),
        initial_budget_yuan:Number(initial.value),monthly_budget_yuan:Number(monthly.value),enabled:enabled.checked,
        taxonomy:taxonomy.value.split('\n').map(x=>x.trim()).filter(Boolean),expected_revision:state.revision}:
        (['resume','cancel','approve','retry-sample','continue-sample'].includes(action)?{job_id}:{});
      const result=await api(endpoint+(action==='save'?'':'/'+action),{method:action==='save'?'PUT':'POST',body,
        headers:{'X-Configuration-Token':state.csrf_token}});
      if(!alive)return;
      messages.replaceChildren(notice(action==='scan'?`发现 ${result.total} 篇；长文 ${result.long_articles} 篇；需识图 ${result.image_articles} 篇。`:
        action==='approve'?'样本已确认。现在可开始全量整理，并开启新增自动整理。':'操作已保存，进度会自动刷新。'));
      await read(['save','switch-profile'].includes(action));
    }catch(e){if(alive)error(e);}finally{busy=false;if(alive)await read().catch(error);}
  }
  const control=(action,label)=>{const b=button(label,()=>perform(action));b.dataset.action=action;controls.push(b);return b;};
  const approve=control('approve','确认这批样本'),all=control('all','开始全量整理'),resume=control('resume','继续任务或恢复自动整理');
  container.append(backLink(configPage?'#/settings':'#/workbench',configPage?'设置':'整理工作台'),pageHeading(configPage?'整理规则与预算':'收藏整理',configPage?'修改分类、模型与自动整理规则。':'查看整理进度，处理需要关注的内容。'),messages);
  if(configPage)container.append(el('section',{className:'card stack'},
      field('原文目录',input),field('整理库目录',output),field('AI 配置名称',profile),
      el('div',{className:'form-grid'},field('首次预算（元）',initial),field('之后每月预算（元）',monthly)),
      field('两级分类',taxonomy,'分类改变后需要重新审核样本。'),el('label',{},enabled,' 自动整理新增收藏（软件运行时）'),
      el('div',{className:'page-actions'},control('save','保存设置'),control('switch-profile','切换模型并保留样式确认'))));
  else container.append(el('section',{className:'card stack'},el('h2',{},'任务与预算'),status,
    el('div',{className:'page-actions'},control('scan','扫描原文'),control('sample','生成 10 篇样本'),all,control('pause','暂停'),resume,control('cancel','结束暂停任务'),
    control('continue','复用响应继续失败条目'),control('retry','手动重试失败条目')),
    notice('手动重试可能产生费用；成功阶段会复用。')),entryGrid([
      ['样本审核','逐篇对照并确认样式','#/organization/review'],['处理记录','分页查看全部内容与失败原因','#/organization/records'],
      ['任务记录','查看进度、暂停和失败任务','#/organization/jobs'],['整理规则与预算','分类、模型与自动整理','#/organization/config'],
    ]));
  await read(true);
  async function poll(){if(!alive)return;if(!busy)await read().catch(error);if(alive)timer=setTimeout(poll,2000);}
  timer=setTimeout(poll,2000);
  return()=>{alive=false;clearTimeout(timer);};
}
