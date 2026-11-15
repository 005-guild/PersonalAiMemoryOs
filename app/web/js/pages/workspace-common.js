import {el} from '../ui.js';

export function entryGrid(entries) {
  return el('div',{className:'entry-grid'},...entries.map(([title,description,href])=>
    el('a',{className:'entry-card',href},el('h2',{},title),el('p',{},description),el('span',{'aria-hidden':'true'},'进入 →'))));
}
export function backLink(href,label='返回') {return el('a',{href,className:'workspace-back'},'← '+label);}
export function safeWorkspaceReturn(value,fallback='#/reading/browse') {
  return /^#\/(reading|sources|knowledge|organization|processing|drafts|search|workbench|settings|system)(?:[/?][^#]*)?$/.test(value||'')?value:fallback;
}
