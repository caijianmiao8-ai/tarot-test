// static/games/ai_duel/main.js

// ====== DOM 快捷 ======
const $ = (s, p=document) => p.querySelector(s);
const $$ = (s, p=document) => p.querySelectorAll(s);

// 关键：确保接口前缀正确，避免 /g/ai_duelapi/... 的 404
const BASE = "/g/ai_duel";

// ====== 元素引用 ======
const chat = $("#chat");
const topic = $("#topic");
const rounds = $("#rounds");
const replyStyle = $("#replyStyle");
const judgeOn = $("#judgeOn");
const judgePerRound = $("#judgePerRound");
const modelA = $("#modelA");
const modelB = $("#modelB");
const judgeModel = $("#judgeModel");
const btnStart = $("#btnStart");
const quotaBox = $("#quotaBox");

// 预设主区
const mainPresetA = $("#mainPresetA");
const mainPresetB = $("#mainPresetB");

// 预设生成器抽屉
const sheet = $("#presetSheet");
const btnOpenSheet = $("#btnOpenPresetSheet");
const btnCloseSheet = $("#btnClosePresetSheet");
const builderModel = $("#builderModel");
const seedInput = $("#presetSeed");
const btnGenPreset = $("#btnGenPreset");
const genSpin = $("#genSpin");
const presetA = $("#presetA");
const presetB = $("#presetB");
const btnUsePreset = $("#btnUsePreset");

// 其它
const bootMask = $("#boot-mask");
const topicChips = $("#topicChips");

// ====== 小工具 ======
function hideBootMask(){ bootMask && bootMask.remove(); }
function scrollToBottom(){ chat && (chat.scrollTop = chat.scrollHeight); }
function escapeHTML(s){ return (s||"").replace(/[&<>]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[m])); }

// ====== 模型列表加载（含 builderModel） ======
async function loadModels(){
  try{
    const r = await fetch(`${BASE}/api/models?available=1`);
    const j = await r.json();
    const list = Array.isArray(j.models) ? j.models : [];

    const fill = (sel) => {
      if(!sel) return;
      sel.innerHTML = "";
      for(const m of list){
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = m.name || m.id;
        sel.appendChild(opt);
      }
    };
    fill(modelA); fill(modelB); fill(judgeModel); fill(builderModel);

    // 合理默认
    if (builderModel && builderModel.options.length){
      const cheap = Array.from(builderModel.options).find(o => /gemma|mistral|deepseek|llama-3\.1-8b|mini|9b/i.test(o.value));
      if (cheap) builderModel.value = cheap.value;
    }
  }catch(e){
    console.warn("loadModels failed:", e);
    // 兜底：至少给一个 demo
    for(const sel of [modelA, modelB, judgeModel, builderModel]){
      if(!sel) continue;
      sel.innerHTML = `<option value="fake/demo">内置演示（无 Key）</option>`;
    }
  }finally{
    hideBootMask();
  }
}

// ====== 配额显示 ======
async function loadQuota(){
  try{
    const r = await fetch(`${BASE}/api/quota`);
    const j = await r.json();
    if(j.ok) quotaBox.textContent = `今日剩余：${j.left}/${j.limit}`;
    else quotaBox.textContent = "配额读取失败";
  }catch(e){
    quotaBox.textContent = "配额读取失败";
  }
}

// ====== 预设生成器：打开/关闭/扩写/应用 ======
btnOpenSheet?.addEventListener("click", () => sheet.setAttribute("aria-hidden", "false"));
btnCloseSheet?.addEventListener("click", () => sheet.setAttribute("aria-hidden", "true"));
$(".sheet__mask")?.addEventListener("click", () => sheet.setAttribute("aria-hidden", "true"));

btnGenPreset?.addEventListener("click", async () => {
  const seed = (seedInput?.value || "").trim();
  if(!seed){ alert("请先输入一句设定"); return; }
  btnGenPreset.disabled = true; genSpin.style.display = "inline-block";
  try{
    const r = await fetch(`${BASE}/api/preset/expand`, {
      method:"POST",
      headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ seed, builderModel: builderModel?.value || "" })
    });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error || "生成失败");
    presetA.value = j.presetA || "";
    presetB.value = j.presetB || "";
  }catch(e){
    alert("扩写失败：" + e.message);
  }finally{
    btnGenPreset.disabled = false; genSpin.style.display = "none";
  }
});

btnUsePreset?.addEventListener("click", () => {
  if (mainPresetA) mainPresetA.value = presetA.value;
  if (mainPresetB) mainPresetB.value = presetB.value;
  sheet.setAttribute("aria-hidden","true");
});

// ====== 话题快捷 Chips ======
topicChips?.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if(!chip) return;
  topic.value = chip.textContent.replace(/\s+/g,"");
});

// ====== 聊天渲染 ======
function makeMsgEl(kind, round, whoLabel){
  const wrap = document.createElement("div");
  wrap.className = `msg ${kind}`; // a | b | j
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = kind === "a" ? "A" : kind==="b" ? "B" : "J";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = whoLabel + (round ? ` · 第 ${round} 轮` : "");
  const text = document.createElement("div");
  text.className = "text streaming";
  bubble.appendChild(meta); bubble.appendChild(text);
  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  chat.appendChild(wrap);
  scrollToBottom();
  return {wrap, bubble, text};
}

function finalizeMsgText(el){
  el.classList.remove("streaming");
  // 超长加折叠
  const raw = el.textContent || "";
  if (raw.length > 320){
    el.classList.add("clamp");
    const tgl = document.createElement("div");
    tgl.className = "toggle";
    tgl.textContent = "展开";
    tgl.addEventListener("click", ()=>{
      if (el.classList.contains("clamp")){
        el.classList.remove("clamp"); tgl.textContent = "收起";
      }else{
        el.classList.add("clamp"); tgl.textContent = "展开";
      }
      scrollToBottom();
    });
    el.parentElement.appendChild(tgl);
  }
}

// ====== 对战流程（流式 NDJSON） ======
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

  // UI 初始化
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
    const left = j?.left ?? 0;
    quotaBox.textContent = `今日次数已用尽（剩余 ${left}）`;
    btnStart.disabled = false;
    return;
  }
  if (!res.ok){
    quotaBox.textContent = `启动失败：${res.status}`;
    btnStart.disabled = false;
    return;
  }

  // 维护当前轮的元素
  let curA = null, curB = null, curJ = null;

  // 逐行读取
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  (function pump(){
    reader.read().then(({done, value})=>{
      if (done){
        btnStart.disabled = false;
        loadQuota(); // 结束后刷新配额
        return;
      }
      buf += decoder.decode(value, {stream:true});
      const lines = buf.split("\n");
      buf = lines.pop(); // 留下一行可能未完整
      for (const line of lines){
        const s = line.trim();
        if(!s) continue;
        let obj = null;
        try{ obj = JSON.parse(s); }catch(e){ continue; }

        switch(obj.type){
          case "meta":
            // 首条 meta，可在聊天区提示信息
            const tip = makeMsgEl("j", null, "系统").text;
            tip.textContent = `主题：${obj.topic} · 回合：${obj.rounds} · 裁判：${obj.judge ? "开" : "关"}`;
            finalizeMsgText(tip);
            break;

          case "preset":
            // 后端扩写的预设（如果前端留空且传了 seed）
            if (mainPresetA && obj.A) mainPresetA.value = obj.A;
            if (mainPresetB && obj.B) mainPresetB.value = obj.B;
            // 在聊天区做个提示
            const pmsg = makeMsgEl("j", null, "系统").text;
            pmsg.textContent = "已根据设定扩写 A/B 预设并应用。";
            finalizeMsgText(pmsg);
            break;

          case "chunk":
            if (obj.side === "A"){
              if (!curA || curA.round !== obj.round){
                const el = makeMsgEl("a", obj.round, "A 方");
                curA = { round: obj.round, el };
              }
              curA.el.text.textContent += obj.delta || "";
              scrollToBottom();
            }else{
              if (!curB || curB.round !== obj.round){
                const el = makeMsgEl("b", obj.round, "B 方");
                curB = { round: obj.round, el };
              }
              curB.el.text.textContent += obj.delta || "";
              scrollToBottom();
            }
            break;

          case "turn":
            if (obj.side === "A" && curA){
              finalizeMsgText(curA.el.text);
            }else if(obj.side==="B" && curB){
              finalizeMsgText(curB.el.text);
            }
            break;

          case "judge_chunk":
            if (!curJ || curJ.round !== obj.round){
              const el = makeMsgEl("j", obj.round, "裁判点评");
              curJ = { round: obj.round, el };
            }
            curJ.el.text.textContent += obj.delta || "";
            scrollToBottom();
            break;

          case "judge_turn":
            if (curJ) finalizeMsgText(curJ.el.text);
            break;

          case "judge_final_chunk":
            if (!curJ || curJ.round !== -1){
              const el = makeMsgEl("j", null, "最终裁决");
              curJ = { round: -1, el };
            }
            curJ.el.text.textContent += obj.delta || "";
            scrollToBottom();
            break;

          case "judge_final":
            if (curJ) finalizeMsgText(curJ.el.text);
            break;

          case "error":
            const em = makeMsgEl(obj.side === "B" ? "b" : (obj.side==="A"?"a":"j"), obj.round || null, "错误").text;
            em.textContent = obj.message || "未知错误";
            finalizeMsgText(em);
            break;

          case "end":
            const endm = makeMsgEl("j", null, "系统").text;
            endm.textContent = "对战结束。";
            finalizeMsgText(endm);
            btnStart.disabled = false;
            loadQuota();
            break;
        }
      }
      pump();
    }).catch(err=>{
      const em = makeMsgEl("j", null, "错误").text;
      em.textContent = "连接中断：" + err.message;
      finalizeMsgText(em);
      btnStart.disabled = false;
      loadQuota();
    });
  })();
}

btnStart?.addEventListener("click", startDuel);

// ====== 启动：加载模型与配额 ======
loadModels();
loadQuota();
