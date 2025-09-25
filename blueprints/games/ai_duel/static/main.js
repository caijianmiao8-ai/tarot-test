const $ = s => document.querySelector(s);
const BASE = (p => p.endsWith("/") ? p : p + "/")(location.pathname);
const logEl = $("#log");
const log = html => { logEl.insertAdjacentHTML("beforeend", `<div class="line">${html}</div>`); logEl.scrollTop = logEl.scrollHeight; };

let aborter = null;
let currentLineEl = null;
let transcript = [];

/* ---------- 启动蒙层进度 ---------- */
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

/* ---------- 模型加载：全量 -> 前端并发预检 -> 只保留可用 ---------- */
const CACHE_KEY = "ai_duel_available_models_v2";
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
  const slots = Array(Math.min(limit, items.length)).fill(0).map(async () => {
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
  await Promise.all(slots);
  return ret;
}

function saveCache(models){
  try{ localStorage.setItem(CACHE_KEY, JSON.stringify({ts: Date.now(), models})); }catch{}
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

function fillSelects(models){
  // builder/judge 与 A/B 使用同一列表
  for(const el of [$("#modelA"), $("#modelB"), $("#builderModel"), $("#judgeModel")]){
    el.innerHTML = "";
    models.forEach(m => el.insertAdjacentHTML("beforeend", `<option value="${m.id}">${m.name || m.id}</option>`));
  }
  // 默认选项稍作友好：A/B 取不同项；裁判默认与 A 相同；builder 默认第一个
  if($("#modelA").options.length > 1){
    $("#modelB").selectedIndex = Math.min(1, $("#modelB").options.length-1);
  }
}

async function loadModels(){
  boot.show();
  const cached = loadCache();
  if(cached && cached.length){
    fillSelects(cached);
    boot.hide();
    refreshModelsInBackground();
    return;
  }
  await refreshModelsInForeground();
}

async function refreshModelsInBackground(){
  try{
    const all = await fetchAllModels();
    const ok = await runPool(all, 8, async m => await checkModel(m.id));
    if(ok.length){ ok.sort((a,b)=>(a.name||a.id).localeCompare(b.name||b.id)); saveCache(ok); }
  }catch{}
}

async function refreshModelsInForeground(){
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
      passed.push({id:"fake/demo", name:"内置演示（无 Key）"});
    }
    passed.sort((a,b)=>(a.name||a.id).localeCompare(b.name||b.id));
    saveCache(passed);
    fillSelects(passed);
  }catch(e){
    console.error(e);
    fillSelects([{id:"fake/demo", name:"内置演示（无 Key）"}]);
  }finally{
    boot.hide();
  }
}

/* ---------- 一键扩写预设 ---------- */
async function expandPreset(){
  const seed = $("#seed").value.trim();
  if(!seed){ alert("请先输入一句设定"); return; }
  $("#btnExpand").disabled = true; $("#btnExpand").textContent = "扩写中…";
  try{
    const r = await fetch(`${BASE}api/preset/expand`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({seed, builderModel: $("#builderModel").value})
    });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error || "扩写失败");
    $("#presetA").value = j.presetA || "";
    $("#presetB").value = j.presetB || "";
  }catch(e){
    alert(e.message || "扩写失败");
  }finally{
    $("#btnExpand").disabled = false; $("#btnExpand").textContent = "一键扩写为 A/B 预设";
  }
}

/* ---------- 流式渲染 ---------- */
function beginLine(side, round, cls=""){
  const label = side==="A" ? "🅰️ A方" : side==="B" ? "🅱️ B方" : "🎓 裁判";
  currentLineEl = document.createElement("div");
  currentLineEl.className = "line" + (cls?` ${cls}`:"");
  currentLineEl.innerHTML = `<b>${label}${round?` · 第 ${round} 回合`:''}</b>：<span class="t"></span>`;
  logEl.appendChild(currentLineEl);
  logEl.scrollTop = logEl.scrollHeight;
}
function appendDelta(delta){
  if(!currentLineEl) return;
  currentLineEl.querySelector(".t").textContent += delta;
}

/* ---------- 开始/停止 ---------- */
async function start(){
  $("#start").disabled = true; $("#stop").disabled = false;
  logEl.innerHTML = ""; transcript = []; currentLineEl = null;

  const body = {
    topic:  $("#topic").value.trim(),
    rounds: +$("#rounds").value,
    modelA: $("#modelA").value,
    modelB: $("#modelB").value,
    presetA: $("#presetA").value.trim(),
    presetB: $("#presetB").value.trim(),
    seed:    $("#seed").value.trim(),            // 若 preset 空，则后端会用 seed 扩写
    builderModel: $("#builderModel").value,
    judge: ($("#judgePerRound").checked || $("#judgeFinal").checked),
    judgePerRound: $("#judgePerRound").checked,
    judgeModel: $("#judgeModel").value
  };
  if(!body.topic){ log("请输入问题/话题"); $("#start").disabled=false; $("#stop").disabled=true; return; }

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
    const td = new TextDecoder();
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
          if(msg.judge) log(`裁判：${msg.judgeModel} · 每轮：${msg.judgePerRound ? "是" : "否"}`);
        }else if(msg.type==="preset"){
          // 后端扩写的预设，直接填入编辑框，用户可继续修改后再开新局
          if(msg.A) $("#presetA").value = msg.A;
          if(msg.B) $("#presetB").value = msg.B;
          log("已根据一句设定扩写 A/B 预设（已填入上方编辑框）");
        }else if(msg.type==="chunk"){
          if(activeSide!==msg.side || activeRound!==msg.round){
            activeSide = msg.side; activeRound = msg.round; beginLine(activeSide, activeRound);
          }
          appendDelta(msg.delta);
        }else if(msg.type==="turn"){
          transcript.push(msg);
          activeSide = null; activeRound = null; currentLineEl = null;
        }else if(msg.type==="judge_chunk"){
          if(activeSide!=="J" || activeRound!==msg.round){
            activeSide = "J"; activeRound = msg.round; beginLine("J", activeRound, "judge");
          }
          appendDelta(msg.delta);
        }else if(msg.type==="judge_turn"){
          activeSide = null; activeRound = null; currentLineEl = null;
        }else if(msg.type==="judge_final_chunk"){
          if(activeSide!=="JFINAL"){
            activeSide = "JFINAL"; activeRound = 0; beginLine("J", 0, "judge");
          }
          appendDelta(msg.delta);
        }else if(msg.type==="judge_final"){
          activeSide = null; activeRound = null; currentLineEl = null;
        }else if(msg.type==="error"){
          const who = msg.side ? `${msg.side} 方` : (msg.who || "未知");
          const rr  = msg.round ? ` 第 ${msg.round} 回合` : "";
          log(`❌ ${who}${rr} 出错：${msg.message}`);
        }else if(msg.type==="end"){
          log("<i>对话结束</i>");
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
        models: {A: $("#modelA").value, B: $("#modelB").value, judge: $("#judgeModel").value},
        transcript
      });
      navigator.sendBeacon?.(`${BASE}track`, new Blob([data], {type:"application/json"}));
    }catch{}
  }
}

function stop(){ if(aborter) aborter.abort(); }

/* ---------- 初始化 ---------- */
window.addEventListener("DOMContentLoaded", async ()=>{
  await loadModels();
  $("#btnExpand").addEventListener("click", expandPreset);
  $("#start").addEventListener("click", start);
  $("#stop").addEventListener("click",  stop);
});
