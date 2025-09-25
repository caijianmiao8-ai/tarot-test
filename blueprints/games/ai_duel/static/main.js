// static/games/ai_duel/main.js
const $ = (sel, root=document)=>root.querySelector(sel);
const $$ = (sel, root=document)=>Array.from(root.querySelectorAll(sel));

const BASE = window.DUEL_BASE || (location.pathname.replace(/\/$/, '/'));

// UI refs
const chat = $("#chat");
const btnStart = $("#btn-start");
const btnStop  = $("#btn-stop");
const topicInp = $("#topic");
const roundsInp= $("#rounds");
const modelA   = $("#modelA");
const modelB   = $("#modelB");
const judgeOn  = $("#useJudge");
const judgeSel = $("#judgeModel");
const presetA  = $("#presetA");
const presetB  = $("#presetB");
const seedInp  = $("#seed");
const sheet    = $("#sheet");
const btnToggle= $("#btn-toggle");
const btnSave  = $("#btn-save");
const quotaEl  = $("#quota");
const modelsInfo = $("#modelsInfo");
const nameAEl  = $("#nameA");
const nameBEl  = $("#nameB");
const modelAName = $("#modelAName");
const modelBName = $("#modelBName");

// boot overlay
const boot = $("#boot"), bar=$("#bar"), bootTip=$("#bootTip");

// state
let controller = null;
let running = false;
let lastBubbleA = null;
let lastBubbleB = null;

// helpers
function logBannerTitle(text){
  const b = $(".banner"); if(!b) return;
  const t = $(".banner-title", b); if(t) t.textContent = text;
}
function addMsg(side, text="", isNew=true){
  const wrap = document.createElement("div");
  wrap.className = `msg ${side}`;
  wrap.innerHTML = `
    <div class="avatar"></div>
    <div class="bubble">${text || '<span class="typing"></span>'}</div>
  `;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return $(".bubble", wrap);
}
function appendChunk(bubble, delta){
  if(!bubble) return;
  // remove typing placeholder if present
  const typing = $(".typing", bubble);
  if(typing) typing.remove();
  bubble.textContent += delta;
  chat.scrollTop = chat.scrollHeight;
}
function setModelLabels(){
  const a = modelA.selectedOptions[0]?.text || "模型 A";
  const b = modelB.selectedOptions[0]?.text || "模型 B";
  modelAName.textContent = a;
  modelBName.textContent = b;
}

// sheet controls
btnToggle.addEventListener("click", ()=> sheet.classList.toggle("open"));
$("#sheetClose").addEventListener("click", ()=> sheet.classList.remove("open"));
btnSave.addEventListener("click", ()=>{
  setModelLabels();
  sheet.classList.remove("open");
});

// quick topic chips
chat.addEventListener("click", (e)=>{
  const btn = e.target.closest(".chip");
  if(!btn || !btn.dataset.topic) return;
  topicInp.value = btn.dataset.topic;
});

// quick role chips
$$(".chip.role").forEach(ch=>{
  ch.addEventListener("click", ()=>{
    const a = ch.dataset.a || "";
    const b = ch.dataset.b || "";
    presetA.value = a;
    presetB.value = b;
  });
});

// boot overlay helpers
function bootShow(){ boot.hidden = false; }
function bootHide(){ boot.hidden = true; }
function bootStep(p, tip){ bar.style.width = `${Math.max(0, Math.min(100, p))}%`; if(tip) bootTip.textContent = tip; }

// models
async function loadModels(){
  bootShow(); bootStep(10, "读取模型缓存…");
  try{
    const r = await fetch(`${BASE}api/models?available=1`);
    const j = await r.json();
    const models = j.models || [{id:"fake/demo", name:"内置演示"}];

    // fill selects
    const fill = (sel)=>{
      sel.innerHTML = "";
      for(const m of models){
        const op = document.createElement("option");
        op.value = m.id; op.textContent = m.name;
        sel.appendChild(op);
      }
    };
    fill(modelA); fill(modelB); fill(judgeSel);

    // sensible defaults：A 选第1个，B 选第2个（若有）
    modelA.selectedIndex = 0;
    modelB.selectedIndex = Math.min(1, modelB.options.length-1);
    judgeSel.selectedIndex = 0;

    setModelLabels();
    modelsInfo.textContent = `已载入 ${models.length} 个可用模型`;
    bootStep(100, "完成");
  }catch(e){
    modelsInfo.textContent = "模型目录载入失败，使用内置演示";
  }finally{
    setTimeout(bootHide, 200);
  }
}

// quota
async function loadQuota(){
  try{
    const r = await fetch(`${BASE}api/quota`);
    const j = await r.json();
    if(j.ok){
      quotaEl.textContent = `今日对战配额：剩 ${j.left}/${j.limit}`;
    }
  }catch{}
}

// streaming
function start(){
  if(running) return;
  const topic = topicInp.value.trim();
  const rounds = Math.max(1, Math.min(parseInt(roundsInp.value||"4",10), 10));
  if(!topic){ topicInp.focus(); return; }

  // reset chat banner
  logBannerTitle("对战进行中");
  lastBubbleA = lastBubbleB = null;

  // payload
  const payload = {
    topic,
    rounds,
    modelA: modelA.value,
    modelB: modelB.value,
    presetA: presetA.value.trim(),
    presetB: presetB.value.trim(),
    seed: seedInp.value.trim(),
    judge: !!judgeOn.checked,
    judgePerRound: true,
    judgeModel: judgeSel.value
  };

  // UI
  btnStart.disabled = true;
  btnStop.disabled = false;
  running = true;
  controller = new AbortController();

  // add first typing bubbles
  lastBubbleA = addMsg('a', "", true);
  lastBubbleB = null; // B 会在 A 之后出现

  stream(payload).catch(err=>{
    addMsg('a', `❌ 错误：${err.message || err}`, true);
  }).finally(()=>{
    running = false;
    btnStart.disabled = false;
    btnStop.disabled = true;
    loadQuota();
  });
}
function stop(){
  try{ controller?.abort(); }catch{}
  running = false;
  btnStart.disabled = false;
  btnStop.disabled = true;
}

async function stream(body){
  const r = await fetch(`${BASE}api/stream`, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body),
    signal: controller.signal
  });

  if(!r.ok){
    try{
      const j = await r.json();
      if(r.status===429 && j.error==="DAILY_LIMIT"){
        addMsg('a', `❌ 今日开始次数已用完（剩余 ${j.left} 次）`, true);
      }else{
        addMsg('a', `❌ 启动失败（${r.status}）：${j.error || 'Unknown'}`, true);
      }
    }catch{
      addMsg('a', `❌ 启动失败（${r.status}）`, true);
    }
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  while(true){
    const {done, value} = await reader.read();
    if(done) break;
    buf += decoder.decode(value, {stream:true});
    let idx;
    while((idx = buf.indexOf("\n")) >= 0){
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx+1);
      if(!line) continue;
      handleEvent(line);
    }
  }
}

// event handler
function handleEvent(line){
  let j;
  try{ j = JSON.parse(line); }catch{ return; }

  switch(j.type){
    case "meta":{
      // 更新面板信息
      if(j.A){ modelAName.textContent = j.A; }
      if(j.B){ modelBName.textContent = j.B; }
      break;
    }
    case "preset":{
      // 系统扩写了角色设定，回填到面板
      if(j.A){ presetA.value = j.A; }
      if(j.B){ presetB.value = j.B; }
      break;
    }
    case "chunk":{
      if(j.side === "A"){
        if(!lastBubbleA) lastBubbleA = addMsg('a', "", true);
        appendChunk(lastBubbleA, j.delta || "");
      }else if(j.side === "B"){
        if(!lastBubbleB) lastBubbleB = addMsg('b', "", true);
        appendChunk(lastBubbleB, j.delta || "");
      }
      break;
    }
    case "turn":{
      if(j.side === "A"){
        if(!lastBubbleA) lastBubbleA = addMsg('a', "", true);
        appendChunk(lastBubbleA, "\n"); //轻微收尾
        // 开始等待 B：先放一个打字框
        lastBubbleB = addMsg('b', "", true);
      }else if(j.side === "B"){
        if(!lastBubbleB) lastBubbleB = addMsg('b', "", true);
        appendChunk(lastBubbleB, "\n");
        // 新一轮 A 的 typing
        lastBubbleA = addMsg('a', "", true);
      }
      break;
    }
    case "judge_chunk":{
      // 裁判流：用居中 banner 简略显示
      ensureJudgeBox().textContent += j.delta || "";
      break;
    }
    case "judge_turn":{
      ensureJudgeBox().textContent += "\n";
      break;
    }
    case "judge_final":{
      ensureJudgeBox().textContent = (j.text || "").trim();
      break;
    }
    case "error":{
      const who = j.side || j.who || "system";
      addMsg('a', `❌ ${who} 出错：${j.message || '未知错误'}`, true);
      break;
    }
    case "end":{
      logBannerTitle("对战结束");
      break;
    }
    default:
      // ignore
  }
}
function ensureJudgeBox(){
  let box = $("#judgeBox");
  if(!box){
    box = document.createElement("div");
    box.id = "judgeBox";
    box.className = "banner";
    box.innerHTML = `<div class="banner-title">裁判点评</div><div class="banner-note"></div>`;
    chat.appendChild(box);
  }
  return $(".banner-note", box);
}

// actions
btnStart.addEventListener("click", start);
btnStop.addEventListener("click", stop);

// enter start
topicInp.addEventListener("keydown", (e)=>{ if(e.key==="Enter") start(); });

// init
(async function init(){
  await loadModels();
  await loadQuota();
})();
