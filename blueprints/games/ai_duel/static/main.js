const $ = s => document.querySelector(s);
const BASE = (p => p.endsWith("/") ? p : p + "/")(location.pathname);
const logEl = $("#log");

let aborter = null;
let currentLineEl = null;
let transcript = [];
let isFirstMessage = true;
let currentMessage = { side: null, content: '', round: null, isJudge: false };

// 清空初始状态
function clearEmptyState() {
  if (isFirstMessage) {
    logEl.innerHTML = "";
    isFirstMessage = false;
  }
}

// 渲染消息 - 新的对话UI
function renderMessage(side, content, round, isJudge = false) {
  clearEmptyState();
  
  let messageClass = isJudge ? 'judge' : `side-${side}`;
  let icon = side === 'A' ? '🅰️' : side === 'B' ? '🅱️' : '🎓';
  let label = side === 'A' ? 'A方' : side === 'B' ? 'B方' : '裁判';
  
  const messageHtml = `
    <div class="message ${messageClass}">
      <div class="message-content">
        <div class="message-header">
          <span>${icon} ${label}</span>
          ${round ? `<span class="round-badge">第 ${round} 回合</span>` : ''}
        </div>
        <div class="message-text">${content}</div>
      </div>
    </div>
  `;
  
  logEl.insertAdjacentHTML('beforeend', messageHtml);
  logEl.scrollTop = logEl.scrollHeight;
}

// 系统消息
function renderSystemMessage(content, isError = false) {
  clearEmptyState();
  const className = isError ? 'error-message' : 'system-message';
  logEl.insertAdjacentHTML('beforeend', `<div class="${className}">${content}</div>`);
  logEl.scrollTop = logEl.scrollHeight;
}

// 配额显示
function renderQuota(left, total) {
  clearEmptyState();
  const quotaHtml = `
    <div class="quota-display">
      <span class="icon">🎫</span>
      <span class="text">今日对战配额：</span>
      <span class="count">${left} / ${total}</span>
    </div>
  `;
  logEl.insertAdjacentHTML('beforeend', quotaHtml);
}

// 流式消息处理
function beginLine(side, round, cls="") {
  // 如果有未完成的消息，先渲染它
  if (currentMessage.content) {
    renderMessage(currentMessage.side, currentMessage.content, currentMessage.round, currentMessage.isJudge);
  }
  
  // 开始新消息
  const isJudge = cls === "judge" || side === "J";
  currentMessage = { 
    side: isJudge ? 'J' : side, 
    content: '', 
    round: round, 
    isJudge: isJudge 
  };
  
  // 创建临时消息元素用于实时更新
  clearEmptyState();
  let messageClass = isJudge ? 'judge' : `side-${side}`;
  let icon = side === 'A' ? '🅰️' : side === 'B' ? '🅱️' : '🎓';
  let label = side === 'A' ? 'A方' : side === 'B' ? 'B方' : '裁判';
  
  const tempMessageHtml = `
    <div class="message ${messageClass}" id="temp-message">
      <div class="message-content">
        <div class="message-header">
          <span>${icon} ${label}</span>
          ${round ? `<span class="round-badge">第 ${round} 回合</span>` : ''}
        </div>
        <div class="message-text" id="temp-text"></div>
      </div>
    </div>
  `;
  
  logEl.insertAdjacentHTML('beforeend', tempMessageHtml);
  currentLineEl = $("#temp-text");
}

function appendDelta(delta) {
  currentMessage.content += delta;
  if (currentLineEl) {
    currentLineEl.textContent = currentMessage.content;
    logEl.scrollTop = logEl.scrollHeight;
  }
}

// 完成当前消息
function finishCurrentMessage() {
  // 移除临时消息
  const tempMsg = $("#temp-message");
  if (tempMsg) tempMsg.remove();
  
  // 渲染最终消息
  if (currentMessage.content) {
    renderMessage(
      currentMessage.side === 'J' ? 'J' : currentMessage.side, 
      currentMessage.content, 
      currentMessage.round, 
      currentMessage.isJudge
    );
  }
  
  // 重置
  currentMessage = { side: null, content: '', round: null, isJudge: false };
  currentLineEl = null;
}

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

/* ---------- 模型加载 ---------- */
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
  try{ localStorage.setItem(CACHE_KEY, JSON.stringify({ts: Date.now(), models}));   }catch{}
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
  $("#btnExpand").disabled = true; 
  $("#btnExpand").textContent = "⏳ 生成中…";
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
    $("#btnExpand").disabled = false; 
    $("#btnExpand").textContent = "✨ 一键生成角色";
  }
}

/* ---------- 开始/停止 ---------- */
async function start(){
  $("#start").disabled = true; 
  $("#stop").disabled = false;
  logEl.innerHTML = '<div class="empty-state"><div class="icon">🦗</div><div class="text">等待开始精彩对决...</div></div>';
  transcript = []; 
  currentLineEl = null;
  isFirstMessage = true;
  currentMessage = { side: null, content: '', round: null, isJudge: false };

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
  
  if(!body.topic){ 
    renderSystemMessage("请输入问题/话题", true);
    $("#start").disabled=false; 
    $("#stop").disabled=true; 
    return; 
  }

  aborter = new AbortController();

  try{
    const r = await fetch(`${BASE}api/stream`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body),
      signal: aborter.signal
    });
    
    if (!r.ok){
      try{
        const j = await r.json();
        if (r.status === 429 && j.error === "DAILY_LIMIT"){
          renderSystemMessage(`⌛ 今日开始次数已用完（剩余 ${j.left} 次）`, true);
        }else{
          renderSystemMessage(`❌ 出错（${r.status}）：${j.error || ""}`, true);
        }
      }catch{
        renderSystemMessage(`❌ 出错（${r.status}）`, true);
      }
      $("#start").disabled = false; 
      $("#stop").disabled = true;
      return;
    }

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
        let msg; 
        try{ msg = JSON.parse(line); } catch{ continue; }

        if(msg.type==="meta"){
          clearEmptyState();
          renderSystemMessage(`📋 题目：<b>${msg.topic}</b>（回合：${msg.rounds}）`);
          if(msg.judge) renderSystemMessage(`🎓 裁判：${msg.judgeModel} · 每轮：${msg.judgePerRound ? "是" : "否"}`);
        }else if(msg.type==="preset"){
          // 后端扩写的预设，直接填入编辑框，用户可继续修改后再开新局
          if(msg.A) $("#presetA").value = msg.A;
          if(msg.B) $("#presetB").value = msg.B;
          renderSystemMessage("✅ 已根据一句设定扩写 A/B 预设");
        }else if(msg.type==="chunk"){
          if(activeSide!==msg.side || activeRound!==msg.round){
            finishCurrentMessage();
            activeSide = msg.side; 
            activeRound = msg.round; 
            beginLine(activeSide, activeRound);
          }
          appendDelta(msg.delta);
        }else if(msg.type==="turn"){
          transcript.push(msg);
          finishCurrentMessage();
          activeSide = null; 
          activeRound = null;
        }else if(msg.type==="judge_chunk"){
          if(activeSide!=="J" || activeRound!==msg.round){
            finishCurrentMessage();
            activeSide = "J"; 
            activeRound = msg.round; 
            beginLine("J", activeRound, "judge");
          }
          appendDelta(msg.delta);
        }else if(msg.type==="judge_turn"){
          finishCurrentMessage();
          activeSide = null; 
          activeRound = null;
        }else if(msg.type==="judge_final_chunk"){
          if(activeSide!=="JFINAL"){
            finishCurrentMessage();
            activeSide = "JFINAL"; 
            activeRound = 0; 
            beginLine("J", 0, "judge");
          }
          appendDelta(msg.delta);
        }else if(msg.type==="judge_final"){
          finishCurrentMessage();
          activeSide = null; 
          activeRound = null;
        }else if(msg.type==="error"){
          const who = msg.side ? `${msg.side} 方` : (msg.who || "未知");
          const rr  = msg.round ? ` 第 ${msg.round} 回合` : "";
          renderSystemMessage(`❌ ${who}${rr} 出错：${msg.message}`, true);
        }else if(msg.type==="end"){
          renderSystemMessage("🏁 对决结束");
        }
      }
    }
    
    // 确保最后的消息被渲染
    finishCurrentMessage();
  }catch(e){
    if(e.name === 'AbortError') {
      renderSystemMessage("⏹ 已停止对话");
    } else {
      renderSystemMessage("⚠️ 网络异常或连接中断", true);
    }
  }finally{
    $("#start").disabled = false; 
    $("#stop").disabled = true;
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

function stop(){ 
  if(aborter) aborter.abort(); 
}

async function showQuota(){
  try{
    const r = await fetch(`${BASE}api/quota`);
    const j = await r.json();
    if(j.ok && j.limit !== undefined){
      renderQuota(j.left, j.limit);
      if(j.left <= 0){ 
        $("#start").disabled = true; 
      }
    }
  }catch{}
}

/* ---------- 初始化 ---------- */
window.addEventListener("DOMContentLoaded", async ()=>{
  await loadModels();
  await showQuota();   // 显示配额
  $("#btnExpand").addEventListener("click", expandPreset);
  $("#start").addEventListener("click", start);
  $("#stop").addEventListener("click",  stop);
});

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
  try{
    boot.update(0, 1, "读取模型列表…");
    // 先尝试从缓存读取
    const cached = loadCache();
    if(cached){
      fillSelects(cached);
      boot.hide();
      // 后台刷新
      refreshModelsInBackground();
      return;
    }
    
    // 没有缓存，前台加载
    await refreshModelsInForeground();
  }catch(e){
    console.error("loadModels error:", e);
    fillSelects([{id:"fake/demo", name:"内置演示（无 Key）"}]);
    boot.hide();
  }
}

async function refreshModelsInBackground(){
  try{
    const all = await fetchAllModels();
    const ok = await runPool(all, 8, async m => await checkModel(m.id));
    if(ok.length){ 
      ok.sort((a,b)=>(a.name||a.id).localeCompare(b.name||b.id)); 
      saveCache(ok); 
    }