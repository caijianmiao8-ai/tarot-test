const $  = (s, r=document)=>r.querySelector(s);
const $$ = (s, r=document)=>Array.from(r.querySelectorAll(s));

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
const modelAName = $("#modelAName");
const modelBName = $("#modelBName");
const toastEl = $("#toast");
const boot = $("#boot"), bar=$("#bar"), bootTip=$("#bootTip");

// 回答长度分段
const lenSeg = $("#lenSeg");
let replyStyle = "short";
lenSeg.addEventListener("click", (e)=>{
  const btn = e.target.closest(".seg-btn"); if(!btn) return;
  $$(".seg-btn", lenSeg).forEach(b=>b.classList.remove("active"));
  btn.classList.add("active");
  replyStyle = btn.dataset.len || "short";
});

// state
let controller = null;
let running = false;
let lastBubbleA = null;
let lastBubbleB = null;

// utils
function toast(msg, ms=2200){ toastEl.textContent = msg; toastEl.hidden = false; setTimeout(()=>toastEl.hidden=true, ms); }
function logBannerTitle(text){ const b=$(".banner"); if(!b) return; const t=$(".banner-title",b); if(t) t.textContent=text; }

// 懒创建：只有在收到第一块 chunk 时，才创建对应泡泡，避免“空打字框”残留
function getBubble(side){
  if(side==="A"){
    if(!lastBubbleA){
      lastBubbleA = createMsg('a');
    }
    return lastBubbleA;
  }else{
    if(!lastBubbleB){
      lastBubbleB = createMsg('b');
    }
    return lastBubbleB;
  }
}
function createMsg(side){
  const wrap = document.createElement("div");
  wrap.className = `msg ${side==='A'?'a':'b'}`;
  wrap.innerHTML = `<div class="bubble"><span class="typing"></span></div><div class="time">${new Date().toLocaleTimeString()}</div>`;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return $(".bubble", wrap);
}
function appendChunk(bubble, delta){
  const typing = $(".typing", bubble);
  if(typing) typing.remove();
  bubble.textContent += delta;
  chat.scrollTop = chat.scrollHeight;
}
function finalizeBubble(bubble){
  if(!bubble) return;
  // 去除 typing，若为空则移除整个消息
  const typing = $(".typing", bubble);
  if(typing) typing.remove();
  const text = bubble.textContent.trim();
  if(!text){
    const msg = bubble.parentElement;
    msg?.parentElement?.removeChild(msg);
    return;
  }
  // 长文折叠
  requestAnimationFrame(()=>{
    if(bubble.scrollHeight > 260){
      bubble.classList.add("collapsed");
      let btn = document.createElement("span");
      btn.className = "more-btn";
      btn.textContent = "展开全文";
      btn.addEventListener("click", ()=>{
        if(bubble.classList.contains("collapsed")){
          bubble.classList.remove("collapsed");
          btn.textContent = "收起";
        }else{
          bubble.classList.add("collapsed");
          btn.textContent = "展开全文";
        }
      });
      bubble.parentElement.appendChild(btn);
    }
  });
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

// 预载遮罩
function bootShow(){ boot.hidden = false; }
function bootHide(){ boot.hidden = true; }
function bootStep(p, tip){ bar.style.width = `${Math.max(0, Math.min(100, p))}%`; if(tip) bootTip.textContent = tip; }

// 模型与配额
async function loadModels(){
  bootShow(); bootStep(20, "加载可用模型…");
  try{
    const r = await fetch(api('api/models?available=1'));
    const j = await r.json();
    const models = j.models || [];
    const fill = (sel)=>{
      sel.innerHTML = "";
      models.forEach(m=>{
        const op = document.createElement("option");
        op.value = m.id; op.textContent = m.name;
        sel.appendChild(op);
      });
    };
    fill(modelA); fill(modelB); fill(judgeSel);
    modelA.selectedIndex = 0;
    modelB.selectedIndex = Math.min(1, modelB.options.length-1);
    judgeSel.selectedIndex = 0;

    modelAName.textContent = modelA.selectedOptions[0]?.text || "模型 A";
    modelBName.textContent = modelB.selectedOptions[0]?.text || "模型 B";
    modelsInfo.textContent = models.length ? `已载入 ${models.length} 个可用模型` : "未获取到可用模型（读缓存失败）";
    bootStep(100, "完成");
  }catch(e){
    modelsInfo.textContent = "模型目录载入失败";
  }finally{
    setTimeout(bootHide, 150);
  }
}
async function loadQuota(){
  try{
    const r = await fetch(api('api/quota'));
    const j = await r.json();
    if(j.ok) quotaEl.textContent = `今日对战配额：剩 ${j.left}/${j.limit}`;
  }catch{}
}

// 设置面板
$("#sheetClose").addEventListener("click", ()=> sheet.classList.remove("open"));
$("#btn-toggle").addEventListener("click", ()=> sheet.classList.toggle("open"));
$("#btn-save").addEventListener("click", ()=>{ 
  modelAName.textContent = modelA.selectedOptions[0]?.text || "模型 A";
  modelBName.textContent = modelB.selectedOptions[0]?.text || "模型 B";
  sheet.classList.remove("open");
});

// 快捷题目/角色
chat.addEventListener("click", (e)=>{
  const c = e.target.closest(".chip");
  if(c?.dataset.topic) topicInp.value = c.dataset.topic;
});
$$(".chip.role").forEach(ch=>{
  ch.addEventListener("click", ()=>{
    presetA.value = ch.dataset.a || "";
    presetB.value = ch.dataset.b || "";
  });
});

// 预设生成（后端 LLM），失败自动退化
btnGen.addEventListener("click", async ()=>{
  const seed = seedInp.value.trim();
  const topic = topicInp.value.trim();
  if(!seed && !topic){ toast("请先填写题目或一句设定"); return; }
  try{
    const r = await fetch(api('api/presets'), {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ topic, seed, modelA: modelA.value, modelB: modelB.value })
    });
    if(r.ok){
      const j = await r.json();
      if(j.ok){
        if(j.presetA) presetA.value = j.presetA;
        if(j.presetB) presetB.value = j.presetB;
        toast("已生成角色预设");
        return;
      }
    }
    fallbackSeed();
  }catch{ fallbackSeed(); }
  function fallbackSeed(){
    if(seed){
      if(!presetA.value) presetA.value = `角色 A：${seed}`;
      if(!presetB.value) presetB.value = `角色 B：${seed}`;
      toast("后端未启用 /api/presets，已用一句设定填入 A/B");
    }else{
      toast("生成失败");
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

  // 重置状态（不提前放“打字框”，避免残留）
  logBannerTitle("对战进行中");
  lastBubbleA = null;
  lastBubbleB = null;

  const payload = {
    topic, rounds,
    modelA: modelA.value, modelB: modelB.value,
    presetA: presetA.value.trim(), presetB: presetB.value.trim(),
    seed: seedInp.value.trim(),
    judge: (judgePer.checked || judgeFinal.checked),
    judgePerRound: !!judgePer.checked,
    judgeFinal: !!judgeFinal.checked,
    judgeModel: judgeSel.value,
    reply_style: replyStyle   // ★ 新增：回答长度偏好
  };

  btnStart.disabled = true;
  btnStop.disabled = false;
  running = true;
  controller = new AbortController();

  stream(payload).catch(err=>{
    getBubble("A"); appendChunk(lastBubbleA, `❌ 错误：${err.message || err}`);
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
        getBubble("A"); appendChunk(lastBubbleA, `❌ 今日开始次数已用完（剩余 ${j.left} 次）`);
      }else{
        getBubble("A"); appendChunk(lastBubbleA, `❌ 启动失败（${r.status}）：${j.error || 'Unknown'}`);
      }
    }catch{
      getBubble("A"); appendChunk(lastBubbleA, `❌ 启动失败（${r.status}）`);
    }
    finalizeAll();
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
  // 正常结束，保底收尾
  finalizeAll();
}

function finalizeAll(){
  finalizeBubble(lastBubbleA);
  finalizeBubble(lastBubbleB);
  // 清理所有 typing 残留 & 空消息
  $$(".bubble").forEach(b=>{
    const t = $(".typing", b); if(t) t.remove();
    if(!b.textContent.trim()){
      const msg = b.parentElement; msg?.parentElement?.removeChild(msg);
    }
  });
}

function handleEvent(line){
  let j; try{ j = JSON.parse(line); }catch{ return; }

  switch(j.type){
    case "meta":{
      if(j.A) modelAName.textContent = j.A;
      if(j.B) modelBName.textContent = j.B;
      break;
    }
    case "preset":{
      if(j.A) presetA.value = j.A;
      if(j.B) presetB.value = j.B;
      break;
    }
    case "chunk":{
      const side = j.side==="B" ? "B" : "A";
      const bubble = getBubble(side);
      appendChunk(bubble, j.delta || "");
      break;
    }
    case "turn":{
      // 仅结束当前说话方；不再“预放下一个打字框”，避免无裁判/最后一轮时出现空框
      if(j.side==="A"){ finalizeBubble(lastBubbleA); }
      else if(j.side==="B"){ finalizeBubble(lastBubbleB); }
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
      getBubble("A"); appendChunk(lastBubbleA, `❌ ${who} 出错：${j.message || '未知错误'}`);
      break;
    }
    case "end":{
      logBannerTitle("对战结束");
      // 收尾由 finalizeAll() 完成
      break;
    }
  }
}

// 初始化
(async function init(){
  bootShow(); await loadModels(); await loadQuota(); bootHide();
})();
