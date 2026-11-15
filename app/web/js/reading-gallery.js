import {el, button} from './ui.js';

export const isCollectionImage = value => /^\/api\/v1\/collection-organization\/assets\/[a-f0-9]{64}\.(?:png|jpg|gif|webp)$/.test(value || '');

export function createGallery(images) {
  const allowed = images.map(image => ({...image,url:isCollectionImage(image.url)?image.url:null}));
  const dialog = el('dialog', {className:'reading-gallery-dialog','aria-label':'原图预览'});
  let position = 0, opener;
  const large = el('img', {alt:''}), caption = el('p', {'aria-live':'polite'});
  const scroll = el('div', {className:'reading-image-scroll',tabIndex:0,'aria-label':'可滚动的图片'},large);
  const previous = button('上一张',()=>show(position-1));
  const next = button('下一张',()=>show(position+1));
  const zoom = button('原尺寸',()=>{
    const active=dialog.classList.toggle('is-zoomed');zoom.setAttribute('aria-pressed',String(active));zoom.textContent=active?'适合窗口':'原尺寸';
  },{'aria-pressed':'false'});
  dialog.append(el('div',{className:'reading-gallery-tools'},button('关闭',()=>dialog.close(),{autofocus:true}),previous,next,zoom),scroll,caption);
  large.addEventListener('error',()=>{caption.textContent=`第 ${position+1} / ${allowed.length} 张 · 图片无法加载，原文仍可阅读。`;large.hidden=true;});
  function show(index) {
    if(index<0 || index>=allowed.length)return;
    position=index;const image=allowed[index];
    large.hidden=!image.url;large.removeAttribute('src');
    if(image.url)large.src=image.url;
    large.alt=image.alt || `原文图片 ${index+1}`;
    dialog.classList.remove('is-zoomed');zoom.setAttribute('aria-pressed','false');zoom.textContent='原尺寸';zoom.disabled=!image.url;
    caption.textContent=`第 ${index+1} / ${allowed.length} 张${image.url?'':' · 图片缺失，原文仍可阅读。'}`;
    previous.disabled=index===0;next.disabled=index===allowed.length-1;scroll.scrollTo(0,0);
  }
  function open(index, trigger) {opener=trigger;show(index);dialog.showModal();}
  dialog.addEventListener('keydown',event=>{
    if(event.altKey||event.ctrlKey||event.metaKey)return;
    if(event.key==='ArrowLeft'){event.preventDefault();show(position-1);}
    if(event.key==='ArrowRight'){event.preventDefault();show(position+1);}
  });
  dialog.addEventListener('close',()=>{large.removeAttribute('src');if(opener?.isConnected)opener.focus({preventScroll:true});});
  function trigger(index, thumbnail=false) {
    const image=allowed[index];
    if(!image?.url)return el('span',{className:'reading-image-missing'},`〔图片 ${index+1} 缺失〕`);
    const control=button(thumbnail?'':`查看图片 ${index+1}`,()=>open(index,control),{className:thumbnail?'reading-thumbnail':'reading-inline-image','aria-label':`放大第 ${index+1} 张图片`});
    if(thumbnail){
      const small=el('img',{src:image.url,alt:image.alt,loading:'lazy',decoding:'async'});
      small.addEventListener('error',()=>{control.replaceChildren(el('span',{},`图片 ${index+1} 无法加载`));control.disabled=true;});
      control.append(small,el('span',{},`图片 ${index+1}`));
    }
    return control;
  }
  return {dialog,images:allowed,trigger,dispose:()=>{if(dialog.open)dialog.close();dialog.remove();}};
}
