// static/games/ai_duel/main.js
const $  = (s, r=document)=>r.querySelector(s);
const $$ = (s, r=document)=>Array.from(r.querySelectorAll(s));

// 安全 BASE & 拼接
const rawBase = window.DUEL_BASE || "/g/ai_duel/";
const BASE = rawBase.endsWith('/') ? rawBase : rawBase + '/';
const api = (p)=> BASE + (p.startsWith('/') ? p.slice(1) : p);

// refs
const chat   = $("#chat");
const btnStart = $("#btn-start");
const btnStop  = $("#btn-stop");
const topicInp = $("#topic");
const roundsInp= $("#rounds");
const modelA   = $("#modelA");
const modelB   = $("#modelB");
const judgeSel = $("#judgeModel");
const judgePer = $("#judgePer");
const judgeFinal = $("#judgeFinal");
const seedInp  = $("#seed");
const btnGen   = $("#btn-gen");
const presetA  = $("#presetA");
const presetB  = $("#presetB");
const sheet    = $("#sheet");
const btnToggle= $("#btn-toggle");
const btnSave  = $("#btn-save");
const quotaEl  = $("#quota");
const modelsInfo = $("#modelsInfo");
const nameAEl  = $("#nameA");
const nameBEl  = $("#nameB");
const modelAName = $("#modelAName");
const modelBName = $("#modelBName");
const toastEl = $("#toast");

// boot overlay
const boot = $("#boot"), bar=$("#bar"), bootTip=$("#bootTip");

// state
let controller = null;
let running = false;
let lastBubbleA = null;
let lastBubbleB = null;

// ui utils
function toast(msg, ms=2200){
  toastEl.textContent = msg;
  toastEl.hidden = false;
  setTimeout(()=> toastEl.hidden = true, ms);
}
function logBannerTitle(text){
  const b = $(".banner"); if(!b) return;
  const t = $(".banner-title", b); if(t) t.textContent = text;
}
function addMsg(side, text="", withTime=true){
  const wrap = document.createElement("div");
  wrap.className = `msg ${side}`;
  const time = withTime ? `<div class="time">${new Date().toLocaleTimeString()}</div>` : '';
  wrap.innerHTML = `
    <div class="bubble">${text || '<span class="typing"></span>'}</div>
    ${time}
  `;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return $(".bubble", wrap);
}
function appendChunk(bubble, delta){
  if(!bubble) return;
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

// sheet
$("#sheetClose").addEventListener("click", ()=> sheet.classList.remove("open"));
btnToggle.addEventListener("click", ()=> sheet.classList.toggle("open"));
btnSave.addEventListener("click", ()=>{ setModelLabels(); sheet.classList.remove("open"); });

// 快捷题目
chat.addEventListener("click", (e)=>{
  const btn = e.target.closest(".chip");
  if(!btn || !btn.dataset.topic) return;
  topicInp.value = btn.dataset.topic;
});

// 快捷角色
$$(".chip.role").forEach(ch=>{
  ch.addEventListener("click", ()=>{
    presetA.value = ch.dataset.a || "";
    presetB.value = ch.dataset.b || "";
  });
});

// boot overlay
function bootShow(){ boot.hidden = false; }
function bootHide(){ boot.hidden = true; }
function bootStep(p, tip){ bar.style.width = `${Math.max(0, Math.min(100, p))}%`; if(tip) bootTip.textContent = tip; }

// models
async function loadModels(){
  bootShow(); bootStep(10, "读取模型缓存…");
  try{
    const r = await fetch(api('api/models?available=1'));
    const j = await r.json();
    const models = j.models || [];

    const fill = (sel)=>{
      sel.innerHTML = "";
      for(const m of models){
        const op = document.createElement("option");
        op.value = m.id; op.textContent = m.name;
        sel.appendChild(op);
      }
    };
    fill(modelA); fill(modelB); fill(judgeSel);

    modelA.selectedIndex = 0;
    modelB.selectedIndex = Math.min(1, modelB.options.length-1);
    judgeSel.selectedIndex = 0;

    setModelLabels();
    modelsInfo.textContent = models.length ? `已载入 ${models.length} 个可用模型` : "未获取到可用模型（请检查缓存）";
    bootStep(100, "完成");
  }catch(e){
    modelsInfo.textContent = "模型目录载入失败";
  }finally{
    setTimeout(bootHide, 200);
  }
}

// quota
async function loadQuota(){
  try{
    const r = await fetch(api('api/quota'));
    const j = await r.json();
    if(j.ok){
      quotaEl.textContent = `今日对战配额：剩 ${j.left}/${j.limit}`;
    }
  }catch{}
}

// 生成预设（依赖后端 /api/presets；若 404 则退化为把 seed 套入）
btnGen.addEventListener("click", async ()=>{
  const seed = seedInp.value.trim();
  const topic = topicInp.value.trim();
  if(!seed && !topic){ toast("请先填写题目或一句设定"); return; }

  try{
    const r = await fetch(api('api/presets'), {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        topic,
        seed,
        modelA: modelA.value,
        modelB: modelB.value
      })
    });
    if(r.ok){
      const j = await r.json();
      if(j.ok){
        presetA.value = j.presetA || presetA.value;
        presetB.value = j.presetB || presetB.value;
        toast("已生成角色预设");
        return;
      }
    }
    // 不 ok：退化
    fallbackSeed();
  }catch(e){
    fallbackSeed();
  }

  function fallbackSeed(){
    if(seed){
      if(!presetA.value) presetA.value = `角色 A：${seed}`;
      if(!presetB.value) presetB.value = `角色 B：${seed}`;
      toast("已用一句设定填入 A/B（后端未启用 /api/presets）");
    }else{
      toast("生成失败，且无一句设定可用");
    }
  }
});

// 启动/停止
btnStart.addEventListener("click", start);
btnStop.addEventListener("click", stop);
topicInp.addEventListener("keydown", (e)=>{ if(e.key==="Enter") start(); });

function start(){
  if(running) return;
  const topic = topicInp.value.trim();
  const rounds = Math.max(1, Math.min(parseInt(roundsInp.value||"4",10), 10));
  if(!topic){ topicInp.focus(); toast("请先填写题目"); return; }

  // 重置视图
  logBannerTitle("对战进行中");
  lastBubbleA = addMsg('a', "", true); // A typing
  lastBubbleB = null;

  // payload（注意保留 judge 逐回合 / 终局）
  const payload = {
    topic,
    rounds,
    modelA: modelA.value,
    modelB: modelB.value,
    presetA: presetA.value.trim(),
    presetB: presetB.value.trim(),
    seed: seedInp.value.trim(),
    judge: (judgePer.checked || judgeFinal.checked),
    judgePerRound: !!judgePer.checked,
    judgeFinal: !!judgeFinal.checked,
    judgeModel: judgeSel.value
  };

  btnStart.disabled = true;
  btnStop.disabled = false;
  running = true;
  controller = new AbortController();

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
  toast("已停止");
}

// 流式
async function stream(body){
  const r = await fetch(api('api/stream'), {
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

function ensureJudgeBox(){
  let box = $("#judgeBox");
  if(!box){
    box = document.createElement("div");
    box.id = "judgeBox";
    box.className = "banner";
    box.innerHTML = `<div class="banner-title">裁判</div><div class="banner-note"></div>`;
    chat.appendChild(box);
  }
  return $(".banner-note", box);
}

// 事件处理（不遗漏：meta、preset、chunk、turn、judge_chunk、judge_turn、judge_final、end、error）
function handleEvent(line){
  let j;
  try{ j = JSON.parse(line); }catch{ return; }

  switch(j.type){
    case "meta":{
      if(j.A){ modelAName.textContent = j.A; }
      if(j.B){ modelBName.textContent = j.B; }
      break;
    }
    case "preset":{
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
        appendChunk(lastBubbleA, "\n");
        lastBubbleB = addMsg('b', "", true); // 轮到 B typing
      }else if(j.side === "B"){
        if(!lastBubbleB) lastBubbleB = addMsg('b', "", true);
        appendChunk(lastBubbleB, "\n");
        lastBubbleA = addMsg('a', "", true); // 新一轮 A typing
      }
      break;
    }
    case "judge_chunk":{
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
      // 兼容服务端扩展类型：忽略
  }
}

// 初始化
(async function init(){
  await loadModels();
  await loadQuota();
})();
