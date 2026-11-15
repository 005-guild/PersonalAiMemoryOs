// Restore lists only after their asynchronous rows have enough height.
const positions=new Map();
export function rememberPosition(hash){
  positions.delete(hash);positions.set(hash,window.scrollY);
  if(positions.size>50)positions.delete(positions.keys().next().value);
}
export function restorePosition(hash,root){
  const position=positions.get(hash);if(!position)return()=>{};
  let observer,timer,frame;
  function stop(){observer?.disconnect();clearTimeout(timer);cancelAnimationFrame(frame);for(const name of ['wheel','pointerdown','keydown'])document.removeEventListener(name,stop);}
  function restore(){
    if(document.documentElement.scrollHeight-window.innerHeight>=position){window.scrollTo(0,position);stop();}
  }
  observer=new MutationObserver(restore);observer.observe(root,{childList:true,subtree:true});
  for(const name of ['wheel','pointerdown','keydown'])document.addEventListener(name,stop,{once:true});
  timer=setTimeout(stop,3000);frame=requestAnimationFrame(restore);return stop;
}
