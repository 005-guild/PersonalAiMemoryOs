import {el} from '../ui.js';
import {summaryReview} from './reading-quality.js';
import {backLink} from './workspace-common.js';

export function mountManagement(root,data,params,alive){
  const from=params.get('from')||'#/reading/browse',href='#/reading/'+data.note.id+'?'+new URLSearchParams({from});
  root.append(backLink(href,'返回阅读'),el('h1',{},'编辑与整理'),el('p',{className:'reading-muted'},data.note.title),
    el('a',{className:'btn',href:'#/knowledge/'+data.note.id+'?'+new URLSearchParams({return_to:href})},'编辑正文与分类'));
  if(data.capabilities?.quality){const body=el('section',{className:'reading-management'});root.append(body);return summaryReview(body,data.note,alive,true);}
  root.append(el('p',{},'本篇为普通知识笔记，可直接编辑；收藏摘要升级仅适用于已整理收藏。'));
}
