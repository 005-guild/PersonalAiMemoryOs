import {api} from '../api.js';
import {el, pageHeading, showError} from '../ui.js';
import {entryGrid} from './workspace-common.js';

export function mount(container) {
  const controller=new AbortController();let disposed=false;
  const counts=el('div',{className:'stat-grid'}),recent=el('section',{className:'card stack'});
  container.append(pageHeading('整理工作台','收集资料、审阅结果，让内容有序进入书架。'),counts,
    entryGrid([
      ['资料库','管理原始内容与来源','#/sources'],['导入资料','先预演，再导入本地文件','#/imports'],
      ['笔记管理','批量操作与回收站','#/knowledge'],['收藏整理','查看进度、样本与失败项','#/organization'],
      ['AI 分析','从资料生成待审核草稿','#/processing'],['草稿箱','对照来源、审阅并采纳','#/drafts'],
    ]),recent);
  async function load(){try{
    const [overview,control]=await Promise.all([api('/api/v1/ui/overview',{signal:controller.signal}),api('/api/v1/collection-organization',{signal:controller.signal})]);
    if(disposed)return;
    counts.replaceChildren(...[['待采纳草稿',overview.ready_drafts,'#/drafts'],['整理失败',control.counts.failed||0,'#/organization/records?status=failed'],['同步冲突',overview.open_conflicts,'#/system/conflicts']].map(([label,count,href])=>
      el('a',{className:'card stat-card',href},el('span',{className:'stat-label'},label),el('strong',{className:'stat-value'},String(count)))));
    recent.replaceChildren(el('div',{className:'section-header'},el('h2',{},'近期收藏任务'),el('a',{href:'#/organization/jobs'},'全部记录 →')),
      ...control.jobs.slice(0,5).map(job=>el('a',{className:'status-row',href:'#/organization/jobs?job='+job.id},el('span',{},job.mode+' · '+job.status),el('small',{},job.created_at.slice(0,10)))));
    if(!control.jobs.length)recent.append(el('p',{className:'muted'},'暂无任务。'));
  }catch(error){if(!disposed&&error.name!=='AbortError')showError(error,recent);}}
  load();return()=>{disposed=true;controller.abort();};
}
