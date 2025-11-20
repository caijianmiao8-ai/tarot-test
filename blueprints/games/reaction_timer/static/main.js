// blueprints/games/reaction_timer/static/main.js
const $ = (sel)=> document.querySelector(sel);
const arena = $("#arena");
const timeEl = $("#time");
const lastEl = $("#last");
const bestEl = $("#best");
const avgEl  = $("#avg");
const btnReset = $("#btnReset");

const STATE = {
  Idle:  "idle",   // 等待开始
  Ready: "ready",  // 刚开始，显示提示
  Wait:  "wait",   // 红灯等待随机时长
  Go:    "go",     // 绿灯计时
};

let state = STATE.Idle;
let timerStart = 0;
let waitHandle = null;
let recent = []; // 最近记录（毫秒）

function setState(next){
  state = next;
  arena.classList.remove("state-idle","state-ready","state-wait","state-go","show-false");
  arena.classList.add(`state-${next}`);
  if(next !== STATE.Go) timeEl.textContent = "0 ms";
}

function randDelay(min=1200, max=3500){
  return Math.floor(Math.random()*(max-min+1))+min;
}

function start(){
  setState(STATE.Ready);
  // 给用户一点点过渡时间再进入 Wait
  setTimeout(()=> {
    setState(STATE.Wait);
    waitHandle = setTimeout(()=>{
      setState(STATE.Go);
      timerStart = performance.now();
    }, randDelay());
  }, 200);
}

function register(ms){
  lastEl.textContent = `${ms} ms`;
  recent.push(ms);
  if(recent.length > 5) recent.shift();
  const best = Math.min(...recent);
  const avg = Math.round(recent.reduce((a,b)=>a+b,0) / recent.length);
  bestEl.textContent = `${best} ms`;
  avgEl.textContent  = `${avg} ms`;
}

function handlePress(){
  switch(state){
    case STATE.Idle:
      start(); break;
    case STATE.Ready:
    case STATE.Wait:
      // 过早点击
      if(waitHandle) clearTimeout(waitHandle);
      arena.classList.add("show-false");
      setTimeout(()=> arena.classList.remove("show-false"), 650);
      setState(STATE.Idle);
      break;
    case STATE.Go:
      const ms = Math.round(performance.now() - timerStart);
      timeEl.textContent = `${ms} ms`;
      register(ms);
      setState(STATE.Idle);
      break;
  }
}

// 事件：点击和空格键
arena.addEventListener("click", handlePress);
arena.addEventListener("keydown", (e)=>{
  if(e.code === "Space"){ e.preventDefault(); handlePress(); }
});
arena.addEventListener("focus", ()=> arena.classList.add("focus"));
arena.addEventListener("blur", ()=> arena.classList.remove("focus"));

// 重置
btnReset.addEventListener("click", ()=>{
  recent = [];
  lastEl.textContent = "—";
  bestEl.textContent = "—";
  avgEl.textContent  = "—";
  setState(STATE.Idle);
});

// 初始
setState(STATE.Idle);
