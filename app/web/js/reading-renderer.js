import {marked} from '../vendor/marked.js';
import DOMPurify from '../vendor/purify.js';
import {el, button} from './ui.js';

// Reuse the same parser/sanitizer, but keep the editor's stricter preview unchanged.
export function readingMarkdown(text, gallery, {foldOriginal=false}={}) {
  const tokens=marked.lexer(String(text || ''));
  const root=el('div',{className:'reading-document'}), cleanup=[];
  const prior=[];let split=-1;
  for(let i=0;i<tokens.length;i++)if(tokens[i].type==='heading'&&tokens[i].depth===2){
    if(foldOriginal&&tokens[i].text==='原文'&&['总结','核心要点','适用条件与局限'].every(name=>prior.includes(name))){split=i;break;}
    prior.push(tokens[i].text);
  }
  function part(items, target) {
    const index=new Map(items.map((token,i)=>[token,i]));
    const prefix='reading-section-'+crypto.randomUUID()+'-';
    const renderer=new marked.Renderer();
    renderer.html=()=>'';
    const imageMap=new Map();
    gallery.images.forEach((image,i)=>{if(image.reference)imageMap.set(image.reference,i);if(image.url)imageMap.set(image.url,i);});
    renderer.image=({href})=>imageMap.has(href)?`<span data-reading-image="${imageMap.get(href)}"></span>`:'〔图片未加载〕';
    renderer.heading=function(token){return `<h${token.depth} data-reading-heading="${index.get(token)}">${this.parser.parseInline(token.tokens)}</h${token.depth}>`;};
    const body=el('div',{className:'reading-prose'});
    const more=button('继续阅读',()=>append(),{className:'reading-more'});
    let cursor=0,disposed=false;
    function append() {
      if(disposed)return;
      const batch=[];let size=0;
      while(cursor<items.length&&(size<20000||!batch.length)){
        const token=items[cursor++];batch.push(token);size+=(token.raw||'').length;
      }
      batch.links=tokens.links;
      const fragment=DOMPurify.sanitize(marked.parser(batch,{renderer,async:false}),{RETURN_DOM_FRAGMENT:true,
        USE_PROFILES:{html:true},FORBID_TAGS:['img','style','input','form','iframe','video','audio'],FORBID_ATTR:['style','id','name']});
      for(const link of fragment.querySelectorAll('a')){
        if(!/^(https?:\/\/|mailto:)/i.test(link.getAttribute('href')||''))link.removeAttribute('href');
        else{link.target='_blank';link.rel='noopener noreferrer';}
      }
      for(const marker of fragment.querySelectorAll('[data-reading-image]'))marker.replaceWith(gallery.trigger(Number(marker.dataset.readingImage)));
      for(const heading of fragment.querySelectorAll('[data-reading-heading]'))heading.id=prefix+heading.dataset.readingHeading;
      body.append(fragment);more.hidden=cursor>=items.length;
      more.textContent=`继续阅读（剩余 ${items.length-cursor} 段）`;
    }
    const headings=items.filter(token=>token.type==='heading'&&token.depth<=2);
    if(headings.length>1){
      const toc=el('nav',{'aria-label':'文章章节',className:'reading-toc'});
      for(const token of headings)toc.append(button(token.text.replace(/[*_`]/g,''),()=>{
        const targetIndex=index.get(token);
        while(cursor<=targetIndex)append();
        body.querySelector('#'+CSS.escape(prefix+targetIndex))?.scrollIntoView({behavior:'smooth',block:'start'});
      }));
      target.append(el('details',{className:'reading-outline'},el('summary',{},'文章目录'),toc));
    }
    target.append(body,more);append();
    cleanup.push(()=>{disposed=true;});
  }
  part(split<0?tokens:tokens.slice(0,split),root);
  if(split>=0){
    const details=el('details',{className:'reading-original-fold'},el('summary',{},'展开整理正文中保留的原文'));
    let mounted=false;
    details.addEventListener('toggle',()=>{if(details.open&&!mounted){mounted=true;part(tokens.slice(split),details);}});
    root.append(details);
  }
  return {element:root,dispose:()=>cleanup.forEach(fn=>fn())};
}
