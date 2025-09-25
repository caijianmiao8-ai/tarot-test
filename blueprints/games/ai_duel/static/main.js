const $ = s => document.querySelector(s);
const BASE = (p => p.endsWith("/") ? p : p + "/")(location.pathname);
const logEl = $("#log");
const log = html => { logEl.insertAdjacentHTML("beforeend", `<div class="line">${html}</div>`); logEl.scrollTop = logEl.scrollHeight; };

let aborter = null;
let currentLineEl = null;
let transcript = [];

// ---- 启动蒙层进度 ----
const boot = {
  el: $("#boot"),
  main: $("#main"),
  tip: $("#boot-tip"),
  bar: $("#boot-bar"),
  pct: $("#boot-pct"),
  show(){ this.el.style.display = "flex"; this.main.style.display = "none"; },
  hide(){ this.el.style.display = "none"; this.main.style.display = ""; },
  update(done, total, text){
    const p = total ? Math.round((done/total)*100) : 0;
    this.bar.style.width = p + "%";
    this.pct.textContent = p + "%";
    if(text) this.tip.textContent = text;
  }
};

// ---- 模型加载：全量 -> 前端并发预检 -> 只保留可用 ----
const CACHE_KEY = "ai_duel_available_models_v1";
const CACHE_TTL = 10*60*1000; // 10min

async function fetchAllModels(){
  const r = await fetch(`${BASE}api/models?available=0`);
  const j = await r.json();
  return j.models || [];
}

async function checkModel(id){
  const r = await fetch(`${BASE}api/models/check`, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({id})
  });
  const j = await r.json();
  return !!j.ok;
}

// 简单并发池
async function runPool(items, limit, worker, onStep){
  const ret = [];
  let idx = 0, done = 0;
  const slot = Array(Math.min(limit, items.length)).fill(0).map(async () => {
    while(idx < items.length){
      const i = idx++;
      const it = items[i];
      let ok = false;
      try{ ok = await worker(it); }catch{}
      if(ok) ret.push(it);
      done++;
      onStep?.(done, items.length, it);
    }
  });
  await Promise.all(slot);
  return ret;
}

function saveCache(models){
  try{
    localStorage.setItem(CACHE_KEY, JSON.stringify({ts: Date.now(), models}));
  }catch{}
}
function loadCache(){
  try{
    const raw = localStorage.getItem(CACHE_KEY);
    if(!raw) return null;
    const obj = JSON.parse(raw);
    if(Date.now() - obj.ts > CACHE_TTL) return null;
    return obj.models || null;
  }catch{ return null; }
}

async function loadModels(){
  boot.show();
  // 先尝试用缓存，能秒开；同时后台刷新
  const cached = loadCache();
  if(cached && cached.length){
    fillSelects(cached);
    boot.hide();
    // 背景静默刷新（不挡交互）
    refreshModelsInBackground();
    return;
  }
  // 没缓存：走完整预检并显示进度
  await refreshModelsInForeground();
}

async function refreshModelsInBackground(){
  try{
    const all = await fetchAllModels();
    const ok = await runPool(all, 8, async m => await checkModel(m.id));
    if(ok.length){
      saveCache(ok);
    }
  }catch{}
}

async function refreshModelsInForeground(){
  try{
    boot.update(0, 0, "获取模型目录…");
    const all = await fetchAllModels();
    if(!all.length){
      boot.update(0, 1, "获取模型目录失败，使用演示模型…");
      fillSelects([{id:"fake/demo", name:"内置演示（无 Key）"}]);
      boot.hide();
      return;
    }
    let ok = [];
    await runPool(all, 8, async m => {
      const res = await checkModel(m.id);
      return res;
    }, (done, total, m) => {
      boot.update(done, total, `检测可用性：${m.name || m.id}`);
    });
    // 过滤出通过的
    ok = all.filter(m => {
      // 通过的会在 runPool 的返回里；为简化，我们再跑一遍 checkModel 结果缓存可扩展，但这里直接再发一次太重
      // 直接用缓存方式：服务端 /api/models/check 会写入缓存；这里再查一次不可行
      // 更稳妥：我们在 runPool 内没有保存通过项的引用，改一下：
    });
  }catch(e){
    console.error(e);
  }
}

// 改造 runPool：把通过项推入外层数组
async function loadModels_final(){
  boot.show();
  try{
    boot.update(0, 0, "获取模型目录…");
    const all = await fetchAllModels();
    if(!all.length){
      fillSelects([{id:"fake/demo", name:"内置演示（无 Key）"}]);
      boot.hide();
      return;
    }
    const passed = [];
    await runPool(all, 8, async m => {
      const ok = await checkModel(m.id);
      if(ok) passed.push(m);
      return ok;
    }, (done, total, m) => {
      boot.update(done, total, `检测可用性：${m.name || m.id}`);
    });
    if(!passed.length){
      // 兜底给一个演示项
      passed.push({id:"fake/demo", name:"内置演示（无 Key）"});
    }
    // 排序并缓存
    passed.sort((a,b)=> (a.name||a.id).localeCompare(b.name||b.id));
    saveCache(passed);
    fillSelects(passed);
  }catch(e){
    console.error(e);
    fillSelects([{id:"fake/demo", name:"内置演示（无 Key）"}]);
  }finally{
    boot.hide();
  }
}

function fillSelects(models){
  for(const el of [$("#modelA"), $("#modelB")]){
    el.innerHTML = "";
    models.forEach(m => el.insertAdjacentHTML("beforeend", `<option value="${m.id}">${m.name || m.id}</option>`));
  }
}

function beginLine(side, round){
  const who = side==="A"?"🅰️ A方":side==="B"?"🅱️ B方":"🎓 裁判";
  currentLineEl = document.createElement("div");
  currentLineEl.className = "line";
  currentLineEl.innerHTML = `<b>${who}${round?` · 第 ${round} 回合`:''}</b>：<span class="t"></span>`;
  logEl.appendChild(currentLineEl);
  logEl.scrollTop = logEl.scrollHeight;
}
function appendDelta(delta){
  if(!currentLineEl) return;
  currentLineEl.querySelector(".t").textContent += delta;
}

async function start(){
  $("#start").disabled = true; $("#stop").disabled = false;
  logEl.innerHTML = ""; transcript = []; currentLineEl = null;

  const body = {
    topic:  $("#topic").value.trim(),
    rounds: +$("#rounds").value,
    modelA: $("#modelA").value, stanceA: $("#stanceA").value.trim() || "正方",
    modelB: $("#modelB").value, stanceB: $("#stanceB").value.trim() || "反方",
    judge:  $("#judge").checked
  };
  if(!body.topic){ log("请输入命题"); $("#start").disabled=false; $("#stop").disabled=true; return; }

  aborter = new AbortController();

  try{
    const r = await fetch(`${BASE}api/stream`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body),
      signal: aborter.signal
    });
    if(!r.ok){ log(`出错了（${r.status}）`); return; }

    const reader = r.body.getReader();
    const td = new TextDecoder(); // UTF-8
    let buf = "";
    let activeSide = null, activeRound = null;

    while(true){
      const {value, done} = await reader.read();
      if(done) break;
      buf += td.decode(value, {stream:true});

      let idx;
      while((idx = buf.indexOf("\n")) >= 0){
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx+1);
        if(!line) continue;
        let msg; try{ msg = JSON.parse(line); } catch{ continue; }

        if(msg.type==="meta"){
          log(`题目：<b>${msg.topic}</b>（回合：${msg.rounds}）`);
          log(`A：${msg.A} · 立场「${msg.stanceA}」 | B：${msg.B} · 立场「${msg.stanceB}」`);
        }else if(msg.type==="chunk"){
          if(activeSide!==msg.side || activeRound!==msg.round){
            activeSide = msg.side; activeRound = msg.round; beginLine(activeSide, activeRound);
          }
          appendDelta(msg.delta);
        }else if(msg.type==="turn"){
          transcript.push(msg);
          activeSide = null; activeRound = null; currentLineEl = null;
        }else if(msg.type==="judge"){
          beginLine("JUDGE", 0);
          appendDelta(msg.text);
          currentLineEl = null;
        }else if(msg.type==="error"){
          log(`❌ ${msg.side} 第 ${msg.round} 回合出错：${msg.message}`);
        }else if(msg.type==="end"){
          log("<i>对战结束</i>");
        }
      }
    }
  }catch(e){
    log("已停止或网络异常");
  }finally{
    $("#start").disabled = false; $("#stop").disabled = true;
    try{
      const data = JSON.stringify({
        topic: $("#topic").value,
        models: {A: $("#modelA").value, B: $("#modelB").value},
        transcript
      });
      navigator.sendBeacon?.(`${BASE}track`, new Blob([data], {type:"application/json"}));
    }catch{}
  }
}

function stop(){
  if(aborter) aborter.abort();
}

window.addEventListener("DOMContentLoaded", async ()=>{
  // 用最终版加载（含进度条）
  await loadModels_final();
  $("#start").addEventListener("click", start);
  $("#stop").addEventListener("click",  stop);
});
