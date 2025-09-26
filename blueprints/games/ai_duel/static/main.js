// static/games/ai_duel/main.js
const $  = (s, p=document) => p.querySelector(s);
const $$ = (s, p=document) => p.querySelectorAll(s);
const BASE = "/g/ai_duel"; // 关键：确保不会变成 /g/ai_duelapi/...

// 命名空间根，确保我们只操作本页面
const ROOT = $("#duel-app");

// 基本元素
const bootMask      = $("#boot-mask", ROOT);
const chat          = $("#chat", ROOT);
const topic         = $("#topic", ROOT);
const rounds        = $("#rounds", ROOT);
const replyStyle    = $("#replyStyle", ROOT);
const judgeOn       = $("#judgeOn", ROOT);
const judgePerRound = $("#judgePerRound", ROOT);
const modelA        = $("#modelA", ROOT);
const modelB        = $("#modelB", ROOT);
const judgeModel    = $("#judgeModel", ROOT);
const btnStart      = $("#btnStart", ROOT);
const quotaBox      = $("#quotaBox", ROOT);

// 预设主区
const mainPresetA   = $("#mainPresetA", ROOT);
const mainPresetB   = $("#mainPresetB", ROOT);

// 预设生成器
const sheet         = $("#presetSheet", ROOT);
const mask          = $(".sheet__mask", sheet);
const btnOpenSheet  = $("#btnOpenPresetSheet", ROOT);
const btnCloseSheet = $("#btnClosePresetSheet", ROOT);
const builderModel  = $("#builderModel", ROOT);
const seedInput     = $("#presetSeed", ROOT);
const btnGenPreset  = $("#btnGenPreset", ROOT);
const genSpin       = $("#genSpin", ROOT);
const presetA       = $("#presetA", ROOT);
const presetB       = $("#presetB", ROOT);
const btnUsePreset  = $("#btnUsePreset", ROOT);

// chips
const topicChips    = $("#topicChips", ROOT);

function hideBootMask(){ bootMask && bootMask.remove(); }
function scrollToBottom(){ if (chat) chat.scrollTop = chat.scrollHeight; }

// 模型目录加载（含 builder）
async function loadModels(){
  try{
    const r = await fetch(`${BASE}/api/models?available=1`);
    const j = await r.json();
    const list = Array.isArray(j.models) ? j.models : [];
    const fill = (sel) => {
      if (!sel) return;
      sel.innerHTML = "";
      for (const m of list){
        const o = document.createElement("option");
        o.value = m.id; o.textContent = m.name || m.id;
        sel.appendChild(o);
      }
    };
    fill(modelA); fill(modelB); fill(judgeModel); fill(builderModel);

    // builder 默认挑一个偏便宜的
    if (builderModel && builderModel.options.length){
      const cheap = Array.from(builderModel.options).find(o => /gemma|mistral|deepseek|llama-3\.1-8b|mini|9b/i.test(o.value));
      if (cheap) builderModel.value = cheap.value;
    }
  }catch(e){
    console.warn("loadModels failed:", e);
    // 兜底避免遮罩卡住
    for (const sel of [modelA, modelB, judgeModel, builderModel]){
      if(!sel) continue;
      sel.innerHTML = `<option value="fake/demo">内置演示（无 Key）</option>`;
    }
  }finally{
    hideBootMask();
  }
}

// 配额显示
async function loadQuota(){
  try{
    const r = await fetch(`${BASE}/api/quota`);
    const j = await r.json();
    if (j.ok) quotaBox.textContent = `今日剩余：${j.left}/${j.limit}`;
    else quotaBox.textContent = `配额读取失败`;
  }catch(e){
    quotaBox.textContent = `配额读取失败`;
  }
}

// —— 预设生成器 —— //
btnOpenSheet?.addEventListener("click", ()=>{
  sheet?.setAttribute("aria-hidden","false");
});
btnCloseSheet?.addEventListener("click", ()=>{
  sheet?.setAttribute("aria-hidden","true");
});
mask?.addEventListener("click", ()=>{
  sheet?.setAttribute("aria-hidden","true");
});

btnGenPreset?.addEventListener("click", async ()=>{
  const seed = (seedInput?.value || "").trim();
  if (!seed){ alert("请先输入一句设定"); return; }
  btnGenPreset.disabled = true; genSpin.style.display = "inline-block";
  try{
    const r = await fetch(`${BASE}/api/preset/expand`, {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ seed, builderModel: builderModel?.value || "" })
    });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || "生成失败");
    if (presetA) presetA.value = j.presetA || "";
    if (presetB) presetB.value = j.presetB || "";
  }catch(e){
    alert("扩写失败：" + e.message);
  }finally{
    btnGenPreset.disabled = false; genSpin.style.display = "none";
  }
});

btnUsePreset?.addEventListener("click", ()=>{
  if (mainPresetA) mainPresetA.value = presetA.value;
  if (mainPresetB) mainPresetB.value = presetB.value;
  sheet?.setAttribute("aria-hidden","true");
});

// 话题快捷 chips
topicChips?.addEventListener("click", (e)=>{
  const chip = e.target.closest(".chip");
  if (!chip) return;
  topic.value = chip.textContent.replace(/\s+/g,"");
});

// 聊天渲染
function makeMsg(kind, round, label){
  const wrap = document.createElement("div");
  wrap.className = `msg ${kind}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = kind==="a"?"A":kind==="b"?"B":"J";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = label + (round ? ` · 第 ${round} 轮` : "");
  const text = document.createElement("div");
  text.className = "text streaming";
  bubble.appendChild(meta); bubble.appendChild(text);
  wrap.appendChild(avatar); wrap.appendChild(bubble);
  chat.appendChild(wrap);
  scrollToBottom();
  return { wrap, text };
}
function finalize(el){
  el.classList.remove("streaming");
  const raw = el.textContent || "";
  if (raw.length > 320){
    el.classList.add("clamp");
    const t = document.createElement("div");
    t.className = "toggle"; t.textContent = "展开";
    t.addEventListener("click", ()=>{
      if (el.classList.contains("clamp")){ el.classList.remove("clamp"); t.textContent="收起"; }
      else { el.classList.add("clamp"); t.textContent="展开"; }
      scrollToBottom();
    });
    el.parentElement.appendChild(t);
  }
}

// 开始对战（流式）
let controller = null;
async function startDuel(){
  const payload = {
    topic: (topic.value || "").trim(),
    rounds: parseInt(rounds.value || "4", 10),
    reply_style: (replyStyle.value || "medium"),
    modelA: modelA?.value || "fake/demo",
    modelB: modelB?.value || "fake/demo",
    judge: !!judgeOn.checked,
    judgePerRound: !!judgePerRound.checked,
    judgeModel: judgeModel?.value || "fake/demo",
    presetA: (mainPresetA?.value || "").trim(),
    presetB: (mainPresetB?.value || "").trim(),
  };
  if (!payload.topic){ alert("请输入主题"); return; }

  chat.innerHTML = "";
  btnStart.disabled = true;
  quotaBox.textContent = "对战进行中…";

  controller = new AbortController();
  const res = await fetch(`${BASE}/api/stream`, {
    method:"POST",
    headers:{ "Content-Type":"application/json" },
    body: JSON.stringify(payload),
    signal: controller.signal
  });

  if (res.status === 429){
    const j = await res.json().catch(()=>({}));
    quotaBox.textContent = `今日次数已用尽（剩余 ${j?.left ?? 0}）`;
    btnStart.disabled = false; return;
  }
  if (!res.ok){
    quotaBox.textContent = `启动失败：${res.status}`;
    btnStart.disabled = false; return;
  }

  let curA=null, curB=null, curJ=null;
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";

  (function pump(){
    reader.read().then(({done, value})=>{
      if (done){
        btnStart.disabled = false; loadQuota(); return;
      }
      buf += dec.decode(value, {stream:true});
      const lines = buf.split("\n"); buf = lines.pop();
      for (const line of lines){
        const s = line.trim(); if (!s) continue;
        let obj=null; try{ obj = JSON.parse(s);}catch{ continue; }

        switch(obj.type){
          case "meta":{
            const t = makeMsg("j", null, "系统").text;
            t.textContent = `主题：${obj.topic} · 回合：${obj.rounds} · 裁判：${obj.judge ? "开" : "关"}`;
            finalize(t);
            break;
          }
          case "preset":{
            if (mainPresetA && obj.A) mainPresetA.value = obj.A;
            if (mainPresetB && obj.B) mainPresetB.value = obj.B;
            const t = makeMsg("j", null, "系统").text;
            t.textContent = "已根据设定扩写 A/B 预设并应用。";
            finalize(t);
            break;
          }
          case "chunk":{
            if (obj.side==="A"){
              if (!curA || curA.round!==obj.round){ const el=makeMsg("a", obj.round, "A 方"); curA={round:obj.round, text:el.text}; }
              curA.text.textContent += obj.delta || "";
            }else{
              if (!curB || curB.round!==obj.round){ const el=makeMsg("b", obj.round, "B 方"); curB={round:obj.round, text:el.text}; }
              curB.text.textContent += obj.delta || "";
            }
            scrollToBottom();
            break;
          }
          case "turn":{
            if (obj.side==="A" && curA) finalize(curA.text);
            if (obj.side==="B" && curB) finalize(curB.text);
            break;
          }
          case "judge_chunk":{
            if (!curJ || curJ.round!==obj.round){ const el=makeMsg("j", obj.round, "裁判点评"); curJ={round:obj.round, text:el.text}; }
            curJ.text.textContent += obj.delta || "";
            scrollToBottom();
            break;
          }
          case "judge_turn":{
            if (curJ) finalize(curJ.text); break;
          }
          case "judge_final_chunk":{
            if (!curJ || curJ.round!==-1){ const el=makeMsg("j", null, "最终裁决"); curJ={round:-1, text:el.text}; }
            curJ.text.textContent += obj.delta || "";
            scrollToBottom();
            break;
          }
          case "judge_final":{
            if (curJ) finalize(curJ.text); break;
          }
          case "error":{
            const kind = obj.side==="A"?"a":obj.side==="B"?"b":"j";
            const t = makeMsg(kind, obj.round||null, "错误").text;
            t.textContent = obj.message || "未知错误";
            finalize(t);
            break;
          }
          case "end":{
            const t = makeMsg("j", null, "系统").text;
            t.textContent = "对战结束。";
            finalize(t);
            btnStart.disabled = false;
            loadQuota();
            break;
          }
        }
      }
      pump();
    }).catch(err=>{
      const t = makeMsg("j", null, "错误").text;
      t.textContent = "连接中断：" + err.message;
      finalize(t);
      btnStart.disabled = false;
      loadQuota();
    });
  })();
}

btnStart?.addEventListener("click", startDuel);

// 初始化
loadModels();
loadQuota();
