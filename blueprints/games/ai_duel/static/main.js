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
  try{
    boot.update(0, 1, "读取模型缓存…");
    const r = await fetch(`${BASE}api/models?available=1`);  // 直接拿可用缓存
    const j = await r.json();
    const models = j.models || [{id:"fake/demo", name:"内置演示（无 Key）"}];
    fillSelects(models);
  }catch(e){
    fillSelects([{id:"fake/demo", name:"内置演示（无 Key）"}]);
  }finally{
    boot.hide();
  }
}

async function refreshModelsInBackground(){
  try{
    const all = await fetchAllModels();
    const ok = await runPool(all, 8, async m => await checkModel(m.id));
    if(ok.length){ ok.