// 1) iOS 视口高度修复（--vh）
(function(){
  const setVh=()=>document.documentElement.style.setProperty('--vh',(window.innerHeight*0.01)+'px');
  setVh();
  addEventListener('resize',setVh,{passive:true});
  addEventListener('orientationchange',setVh,{passive:true});
})();

// 2) PWA：注册 Service Worker（静默失败即可）
if ('serviceWorker' in navigator) {
  addEventListener('load', ()=>{
    navigator.serviceWorker.register('/static/sw.js').catch(()=>{});
  });
}

// 3) 独立模式检测（iOS：navigator.standalone；其他：display-mode）
(function(){
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
  if (isStandalone) document.documentElement.classList.add('standalone');
})();
