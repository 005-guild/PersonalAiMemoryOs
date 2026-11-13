import {api} from '../api.js';
import {el,button,field,notice,renderMarkdown,pageHeading,formatDate} from '../ui.js';
import {collectionSearch} from './organization-search.js';

const endpoint='/api/v1/collection-organization';
const labels={discovered:'待整理',ready:'摘要已生成',published:'已入库',failed:'失败',pending:'等待执行',running:'执行中',paused:'已暂停',completed:'完成',completed_with_errors:'部分失败'};
const errors={sample_approval_required:'请先查看并确认样本。',sample_not_ready:'样本尚未全部完成。',
  organization_busy:'已有任务执行中。',paused_job_exists:'请先继续已暂停的任务。',configuration_changed:'配置已变化，请刷新后重试。',
  configuration_incomplete:'请先保存输入和输出目录。',organization_paths_locked:'已有整理记录，不能直接更换目录。',
  organization_budget_exhausted:'本期预算不足，已暂停。可调高预算后继续；跨月任务继续时按当月预算检查。',
  explicit_retry_required:'上次模型请求结果不确定或校验失败，未自动重试。',organization_output_invalid:'模型结果未通过格式或原文依据校验。',
  image_needs_review:'图片内容不够清晰，需要人工检查。',source_changed:'原文或图片已变化，已停止该条整理。',
  export_conflict:'整理文件被外部修改，已保留修改；请核对后恢复原导出文件，再手动重试。',
  organization_profile_unsupported:'请选择官方 DeepSeek 的 deepseek-flash / openai_chat 配置。',
  organization_configuration_invalid:'请检查 AI 配置、模型、密钥和目录。',configuration_read_only:'当前实例为只读模式。'};
const explain=code=>errors[code]||code;

export async function mount(container,context) {
  let alive=true,dirty=false,busy=false,state,timer,sampleSignature='';
  const messages=el('div'),status=el('div'),samples=el('div',{className:'stack'}),failures=el('div');
  const sampleReview=el('details',{className:'card stack'},el('summary',{},'样本审核'),samples);
  const searchPanel=collectionSearch(()=>alive);
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
    if(fill||state?.approved!==value.approved)sampleReview.open=!value.approved;
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
    for(const f of fields)f.disabled=busy||value.read_only;
    for(const c of controls)c.disabled=busy||value.read_only;
    approve.disabled=busy||value.read_only||value.approved||!value.jobs.some(j=>j.id===value.sample_job_id&&j.status==='completed');
    all.disabled=busy||value.read_only||!value.approved;
    resume.disabled=busy||value.read_only||!value.jobs.some(j=>j.status==='paused');
    const sample=value.jobs.find(j=>j.id===value.sample_job_id);
    const signature=sample?.id+':'+sample?.status+':'+(value.counts.ready||0)+':'+(value.counts.failed||0);
    if(sample&&signature!==sampleSignature){
      const data=await api(endpoint+'/items?limit=100&job_id='+sample.id);if(!alive)return;sampleSignature=signature;
      samples.replaceChildren(el('p',{className:'muted'},'检查标题、分类、摘要和依据。确认后才能开始全量整理。'),
        ...data.items.map(item=>el('article',{className:'card stack'},el('h3',{},item.result?.title||item.title),
          el('p',{className:'muted'},`${labels[item.status]||item.status} · 原文 ${item.body_chars} 字符 · ${item.image_count} 张图${item.image_required?' · 需图片识读':''}`),
          item.error&&notice(explain(item.error),'warning'),item.result&&el('div',{},
            el('p',{},item.result.category+' · '+item.result.tags.join(' / ')),el('p',{},item.result.summary),
            el('ul',{},...item.result.points.map(x=>el('li',{},x))),el('p',{},'适用条件与局限：'+item.result.conditions),
            ...item.result.quotes.map(x=>el('blockquote',{},x)),
            item.result.image_observations?.length>0&&el('details',{},el('summary',{},'图片识读记录'),...item.result.image_observations.map(x=>el('p',{},x.text)))),
          el('details',{},el('summary',{},'对照原文：'+item.title),renderMarkdown(item.original.content)),
          el('a',{href:item.original.url,target:'_blank',rel:'noopener noreferrer'},'打开知乎原文'))));
    }
  }
  async function perform(action){
    if(busy||!state)return;
    if(dirty&&action!=='save'&&action!=='pause'){messages.replaceChildren(notice('请先保存设置。','warning'));return;}
    if(action==='save'&&!fields.every(x=>x.reportValidity()))return;
    busy=true;messages.replaceChildren();
    for(const element of [...controls,...fields])element.disabled=true;
    try{
      const job_id=['resume','cancel'].includes(action)?state.jobs.find(j=>j.status==='paused')?.id:state.sample_job_id;
      const body=action==='save'?{input_dir:input.value.trim(),output_dir:output.value.trim(),profile_id:profile.value.trim(),
        initial_budget_yuan:Number(initial.value),monthly_budget_yuan:Number(monthly.value),enabled:enabled.checked,
        taxonomy:taxonomy.value.split('\n').map(x=>x.trim()).filter(Boolean),expected_revision:state.revision}:
        (['resume','cancel','approve','retry-sample','continue-sample'].includes(action)?{job_id}:{});
      const result=await api(endpoint+(action==='save'?'':'/'+action),{method:action==='save'?'PUT':'POST',body,
        headers:{'X-Configuration-Token':state.csrf_token}});
      if(!alive)return;
      messages.replaceChildren(notice(action==='scan'?`发现 ${result.total} 篇；长文 ${result.long_articles} 篇；需识图 ${result.image_articles} 篇。`:
        action==='approve'?'样本已确认。现在可开始全量整理，并开启新增自动整理。':'操作已保存，进度会自动刷新。'));
      await read(action==='save');
    }catch(e){if(alive)error(e);}finally{busy=false;if(alive)await read().catch(error);}
  }
  const control=(action,label)=>{const b=button(label,()=>perform(action));controls.push(b);return b;};
  const approve=control('approve','确认这批样本'),all=control('all','开始全量整理'),resume=control('resume','继续暂停任务');
  container.append(pageHeading('收藏整理','逐篇摘要、自动分类与新标题，保留完整原文和来源。'),
    button('跳到快速检索',()=>{searchPanel.scrollIntoView({block:'start'});searchPanel.querySelector('input')?.focus({preventScroll:true});}),messages,
    el('section',{className:'card stack'},el('h2',{},'整理设置'),
      notice('首次先生成最多 10 篇样本，覆盖普通文章、长文和图片为主的内容。原始 articles 不会被修改。'),
      field('原文目录',input),field('整理库目录',output),field('AI 配置名称',profile),
      el('div',{className:'form-grid'},field('首次预算（元）',initial),field('之后每月预算（元）',monthly)),
      field('两级分类',taxonomy,'分类改变后需要重新审核样本。预算是保守估算，实际账单以 DeepSeek 为准。'),
      el('label',{},enabled,' 样本确认后，自动整理新增收藏（软件运行时）'),
      el('div',{className:'page-actions'},control('save','保存设置'),control('scan','扫描原文'),control('sample','生成 10 篇样本'))),
    el('section',{className:'card stack'},el('h2',{},'任务与预算'),status,
      el('div',{className:'page-actions'},approve,all,control('pause','暂停'),resume,control('cancel','结束暂停任务'),
        control('continue-sample','复用响应继续样本'),control('retry-sample','手动重试失败样本'),
        control('continue','复用响应继续失败条目'),control('retry','手动重试失败条目')),
      notice('失败或超时的模型请求不会自动重试。手动重试可能产生新的费用；已成功的阶段会复用。'),
      button('查看全部处理记录',async()=>{try{const data=await api(endpoint+'/items?limit=100');if(alive)failures.replaceChildren(
        el('p',{},`显示前 ${data.items.length} / ${data.total} 篇`),...data.items.map(x=>el('p',{},`${x.title} · ${labels[x.status]}${x.error?' · '+explain(x.error):''}`)));}catch(e){error(e);}}),failures),
    searchPanel,sampleReview);
  await read(true);
  async function poll(){if(!alive)return;if(!busy)await read().catch(error);if(alive)timer=setTimeout(poll,2000);}
  timer=setTimeout(poll,2000);
  return()=>{alive=false;clearTimeout(timer);};
}
