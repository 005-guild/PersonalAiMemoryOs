import {el,button,notice} from '../ui.js';

export function partialImageReview(onApprove) {
  const list=el('div',{className:'stack'});
  const element=el('section',{className:'card stack',hidden:true},el('h2',{},'待审核图片'),list);
  function render(items,disabled=false) {
    element.hidden=!items.length;
    list.replaceChildren(...items.map(item=>{
      const approve=button('允许此篇仅按清晰内容总结',()=>onApprove(item));
      approve.disabled=disabled;
      return el('article',{className:'stack'},el('h3',{},item.title),
        notice('图片中有无法可靠辨认的部分。允许后仅使用清晰分片，摘要会注明不完整；仅适用于当前这篇原文。','warning'),
        el('a',{href:item.original.url,target:'_blank',rel:'noopener noreferrer'},'对照知乎原文'),approve);
    }));
  }
  return {element,render};
}
