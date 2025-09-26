const $  = (s, p=document) => p.querySelector(s);
const ROOT = $("#duel-app");

// DOM
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
const btnStop       = $("#btnStop", ROOT);
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

// 相对路径，避免 404
const api = (p) => `./api/${p}`;

// ===== 启动遮罩：最多 1.2s =====
const hideBootSoon = setTimeout(() => hideBoot(), 1200);
function hideBoot(){ bootMask && bootMask.remove(); }

// ===== 模型目录缓存（30 天） =====
const CACHE_KEY = "ai_duel_models_v2";
const CACHE_TTL_MS = 30 * 24 * 3600 * 1000;

function getCache(){
  try{
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (!obj.time || !obj.models) return null;
    if (Date.now() - obj.time > CACHE_TTL_MS) return null;
    return obj.models;
  }catch{ return null; }
}
function setCache(models){
  try{ localStorage.setItem(CACHE_KEY, JSON.stringify({ time: Date.now(), models })) }catch{}
}

// 填充下拉
function fillModels(list){
  const sels = [modelA, modelB, judgeModel, builderModel];
  for (const sel of sels){
    if (!sel) continue;
    sel.innerHTML = "";
    list.forEach(m=>{
      const o = document.createElement("option");
      o.value = m.id; o.textContent = m.name || m.id;
      sel.appendChild(o);
    });
  }
  // builder 选相对便宜的
  if (builderModel && builderModel.options.length){
    const cheap = Array.from(builderModel.options).find(o => /gemma|mistral|deepseek|mini|9b|8b|sonar-mini|llama-3\.1-8b/i.test(o.value));
    if (cheap) builderModel.value = cheap.value;
  }
}

// 加载模型（失败不阻塞）
async function loadModels(){
  // 1) 先用缓存（如有）
  const cached = getCache();
  if (cached && cached.length){
    fillModels(cached);
    hideBoot(); clearTimeout(hideBootSoon);
  }else{
    // 没缓存先用兜底项，避免空白
    fillModels([{id:"fake/demo", name:"内置演示（无 Key）"}]);
  }

  // 2) 静默拉最新（有超时保护）
  try{
    const r = await Promise.race([
      fetch(api("models?available=1")),
      new Promise((_, rej)=> setTimeout(()=>rej(new Error("timeout")), 5000))
    ]);
    const j = await r.json();
    if (j && Array.isArray(j.models) && j.models.length){
      fillModels(j.models);
      setCache(j.models);
    }
  }catch(e){
    console.warn("models refresh failed:", e.message);
  }finally{
    hideBoot(); clearTimeout(hideBootSoon);
  }
}

// 配额显示
async function loadQuota(){
  try{
    const r = await fetch(api("quota"));
    const j = await r.json();
    if (j.ok) quotaBox.textContent = `今日剩余：${j.left}/${j.limit}`;
    else quotaBox.textContent = `配额读取失败`;
  }catch(e){
    quotaBox.textContent = `配额读取失败`;
  }
}

// —— 预设生成器 —— //
btnOpenSheet?.addEventListener("click", ()=> sheet?.setAttribute("aria-hidden","false"));
btnCloseSheet?.addEventListener("click", ()=> sheet?.setAttribute("aria-hidden","true"));
mask?.addEventListener("click", ()=> sheet?.setAttribute("aria-hidden","true"));

btnGenPreset?.addEventListener("click", async ()=>{
  const seed = (seedInput?.value || "").trim();
  if (!seed){ alert("请先输入一句设定"); return; }
  btnGenPreset.disabled = true; genSpin.style.display = "inline-block";
  try{
    const r = await fetch(api("preset/expand"), {
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

// 快捷话题
$("#topicChips", ROOT)?.addEventListener("click", (e)=>{
  const chip = e.target.closest(".chip");
  if (!chip) return;
  topic.value = chip.textContent.replace(/\s+/g,"");
});

// 聊天渲染
function scrollToBottom(){ if (chat) chat.scrollTop = chat.scrollHeight; }
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
function clampIfLong(el){
  const raw = el.textContent || "";
  if (raw.length > 320){
    el.classList.add("clamp");
    const t = document.createElement("div");
    t.className = "toggle-more"; t.textContent = "展开";
    t.addEventListener("click", ()=>{
      if (el.classList.contains("clamp")){ el.classList.remove("clamp"); t.textContent="收起"; }
      else { el.classList.add("clamp"); t.textContent="展开"; }
      scrollToBottom();
    });
    el.parentElement.appendChild(t);
  }
}
function finalize(el){
  el.classList.remove("streaming");
  clampIfLong(el);
}

// 开始/停止
let controller = null;
function setRunning(on){
  btnStart.disabled = on;
  btnStop.disabled  = !on;
}

btnStop?.addEventListener("click", ()=>{
  if (controller){ controller.abort(); }
  setRunning(false);
  const t = makeMsg("j", null, "系统").text;
  t.textContent = "已停止对战。";
  finalize(t);
  loadQuota();
});

// 开始对战（NDJSON 流）
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
  setRunning(true);
  quotaBox.textContent = "对战进行中…";

  controller = new AbortController();
  let res;
  try{
    res = await fetch(api("stream"), {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
  }catch(e){
    setRunning(false);
    const t = makeMsg("j", null, "错误").text; t.textContent = "连接失败：" + e.message; finalize(t);
    return;
  }

  if (res.status === 429){
    const j = await res.json().catch(()=>({}));
    quotaBox.textContent = `今日次数已用尽（剩余 ${j?.left ?? 0}）`;
    setRunning(false); return;
  }
  if (!res.ok){
    quotaBox.textContent = `启动失败：${res.status}`;
    const t = makeMsg("j", null, "错误").text; t.textContent = "服务器返回错误"; finalize(t);
    setRunning(false); return;
  }

  let curA=null, curB=null, curJ=null;
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";

  (function pump(){
    reader.read().then(({done, value})=>{
      if (done){
        setRunning(false); loadQuota(); return;
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
              if (!curA || curA.round!==obj.round){ const el=makeMsg("a", obj.round, "A 方"); curA={round:obj.round, text:el.text, seen:true}; }
              curA.text.textContent += (obj.delta || "");
            }else{
              if (!curB || curB.round!==obj.round){ const el=makeMsg("b", obj.round, "B 方"); curB={round:obj.round, text:el.text, seen:true}; }
              curB.text.textContent += (obj.delta || "");
            }
            break;
          }
          case "turn":{
            // ★ 关键兜底：有些模型不发 chunk，只在 turn 给完整文本
            if (obj.side==="A"){
              if (!curA || curA.round!==obj.round){
                const el = makeMsg("a", obj.round, "A 方");
                el.text.textContent = (obj.text || "（无回应）");
                finalize(el.text);
                curA = { round: obj.round, text: el.text, seen: false };
              }else{
                if (!curA.text.textContent.trim()){
                  curA.text.textContent = (obj.text || "（无回应）");
                }
                finalize(curA.text);
              }
            }else{
              if (!curB || curB.round!==obj.round){
                const el = makeMsg("b", obj.round, "B 方");
                el.text.textContent = (obj.text || "（无回应）");
                finalize(el.text);
                curB = { round: obj.round, text: el.text, seen: false };
              }else{
                if (!curB.text.textContent.trim()){
                  curB.text.textContent = (obj.text || "（无回应）");
                }
                finalize(curB.text);
              }
            }
            break;
          }
          case "judge_chunk":{
            if (!curJ || curJ.round!==obj.round){ const el=makeMsg("j", obj.round, "裁判点评"); curJ={round:obj.round, text:el.text}; }
            curJ.text.textContent += (obj.delta || "");
            break;
          }
          case "judge_turn":{
            if (curJ){
              if (!curJ.text.textContent.trim()){
                curJ.text.textContent = (obj.text || "（无回应）");
              }
              finalize(curJ.text);
            }
            break;
          }
          case "judge_final_chunk":{
            if (!curJ || curJ.round!==-1){ const el=makeMsg("j", null, "最终裁决"); curJ={round:-1, text:el.text}; }
            curJ.text.textContent += (obj.delta || "");
            break;
          }
          case "judge_final":{
            if (curJ){
              if (!curJ.text.textContent.trim()){
                curJ.text.textContent = (obj.text || "（无回应）");
              }
              finalize(curJ.text);
            }
            break;
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
            setRunning(false);
            loadQuota();
            break;
          }
        }
      }
      scrollToBottom();
      pump();
    }).catch(err=>{
      const t = makeMsg("j", null, "错误").text;
      t.textContent = "连接中断：" + err.message;
      finalize(t);
      setRunning(false);
      loadQuota();
    });
  })();
}

btnStart?.addEventListener("click", startDuel);

// 初始化
loadModels();
loadQuota();
