import {el, button} from '../ui.js';
import {createGallery} from '../reading-gallery.js';
import {readingMarkdown} from '../reading-renderer.js';
import {browseLink, localDate, safeReturn} from './reading-common.js';

export function mountNote(root,data,params,alive) {
  const {note,original}=data,from=safeReturn(params.get('from'));
  const gallery=createGallery(data.images),documents=[];
  root.append(gallery.dialog);
  const header=el('header',{className:'reading-note-head'},el('a',{href:from,className:'reading-back'},'← 返回阅读列表'),
    el('div',{className:'reading-kicker'},el('a',{href:browseLink({category:note.category||'未分类'})},note.category||'未分类'),
      el('span',{},'更新于 '+localDate(note.updated_at))),el('h1',{},note.title),
    el('p',{className:'reading-muted'},`${original.author||'作者未注明'} · 整理自知乎收藏`),
    el('div',{className:'reading-note-actions'},el('a',{href:`#/knowledge/${note.id}`,className:'reading-secondary'},'编辑笔记'),
      /^https?:\/\//i.test(original.url||'')?el('a',{href:original.url,target:'_blank',rel:'noopener noreferrer'},'查看知乎来源 ↗'):null));
  root.append(header);
  if(data.partial_image_summary)root.append(el('p',{className:'reading-status',role:'status'},'部分图片文字无法辨认。本摘要仅依据清晰内容，不代表截图全文。'));
  if(note.summary)root.append(el('section',{className:'reading-abstract'},el('h2',{},'摘要'),el('p',{},note.summary)));
  if(note.tags.length)root.append(el('div',{className:'reading-note-tags'},...note.tags.map(tag=>el('a',{href:browseLink({tag})},tag))));
  const tabs=el('div',{className:'reading-tabs',role:'tablist','aria-label':'阅读内容'});
  const panels=el('div',{className:'reading-panels'}),notePanel=el('section',{role:'tabpanel',id:'reading-note-panel'}),originalPanel=el('section',{role:'tabpanel',id:'reading-original-panel',hidden:true});
  const noteTab=button('整理笔记',()=>choose(false),{role:'tab',id:'reading-note-tab','aria-controls':notePanel.id});
  const originalTab=button('整理时原文',()=>choose(true),{role:'tab',id:'reading-original-tab','aria-controls':originalPanel.id});
  notePanel.setAttribute('aria-labelledby',noteTab.id);originalPanel.setAttribute('aria-labelledby',originalTab.id);
  let originalMounted=false;
  function choose(originalSelected){
    if(!alive())return;
    for(const [tab,selected] of [[noteTab,!originalSelected],[originalTab,originalSelected]]){
      tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;tab.classList.toggle('active',selected);
    }
    notePanel.hidden=originalSelected;originalPanel.hidden=!originalSelected;
    if(originalSelected&&!originalMounted){
      originalMounted=true;
      originalPanel.append(el('header',{className:'reading-original-heading'},el('h2',{},original.title),
        el('p',{className:'reading-muted'},'这是本篇整理时保存的原文快照；原题和原作者保留。')));
      const doc=readingMarkdown(original.content,gallery);documents.push(doc);originalPanel.append(doc.element);
      if(data.images.length)originalPanel.append(el('section',{className:'reading-images'},el('h2',{},`原文配图 · ${data.images.length}`),
        el('div',{className:'reading-image-grid'},...data.images.map((_,i)=>gallery.trigger(i,true)))));
    }
  }
  tabs.append(noteTab,originalTab);
  tabs.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
    event.preventDefault();const originalSelected=event.key==='End'||(event.key!=='Home'&&document.activeElement===noteTab);choose(originalSelected);(originalSelected?originalTab:noteTab).focus();
  }});
  const rendered=readingMarkdown(note.body,gallery,{foldOriginal:true});documents.push(rendered);notePanel.append(rendered.element);
  panels.append(notePanel,originalPanel);root.append(tabs,panels);choose(false);
  window.scrollTo(0,0);
  return ()=>{documents.forEach(doc=>doc.dispose());gallery.dispose();};
}
