// static/games/ai_duel/main.js
const BASE = document.body.dataset.base.replace(/\/?$/, "/");
const api = (p) => BASE + "api/" + p.replace(/^\//, "");

// DOM
const $ = (id) => document.getElementById(id);
const el = {
  quota: $("quota"),
  modelsState: $("models-state"),
  battleState: $("battle-state"),
  chat: $("chat"),

  toggleSettings: $("toggle-settings"),
  settings: $("settings"),

  topic: $("topic"),
  chips: document.querySelectorAll(".chip"),
  modelA: $("modelA"),
  modelB: $("modelB"),
  judgeModel: $("judge-model"),
  rounds: $("rounds"),
  replyStyle: $("reply-style"),
  sharePersona: $("share-persona"),
  judgeOn: $("judge-on"),
  judgePerRound: $("judge-per-round"),

  start: $("start"),
  stop: $("stop"),
  refreshModels: $("refresh-models"),

  seed: $("seed"),
  builderModel: $("builder-model"),
  btnBuild: $("btn-build"),
  presetA: $("presetA"),
  presetB: $("presetB"),

  toast: $("toast"),
};

let controller = null;
let inBattle = false;
let models = [{ id: "fake/demo", name: "内置演示（无 Key）" }];

// Utils
function toast(msg, ms = 2200) {
  el.toast.textContent = msg;
  el.toast.hidden = false;
  setTimeout(() => (el.toast.hidden = true), ms);
}
function pill(node, text) { node.textContent = text; }
function setBattleState(s) { pill(el.battleState, `状态：${s}`); }
function setModelsState(s) { pill(el.modelsState, `模型目录：${s}`); }
function clampRounds() {
  const v = Math.max(1, Math.min(10, parseInt(el.rounds.value || "4", 10)));
  el.rounds.value = String(v);
}

// Settings drawer (非遮罩)
el.toggleSettings.addEventListener("click", () => {
  el.settings.classList.toggle("open");
});

// 填充 select
function optionize(select, list, keep = "") {
  const prev = select.value;
  select.innerHTML = "";
  list.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.name || m.id;
    select.appendChild(opt);
  });
  if (keep && list.some((x) => x.id === keep)) select.value = keep;
  else if (prev && list.some((x) => x.id === prev)) select.value = prev;
  else if (list[0]) select.value = list[0].id;
}

// 加载模型目录（异步，不阻塞 UI）
async function loadModels() {
  try {
    setModelsState("加载中…");
    const r = await fetch(api("models"));
    const j = await r.json();
    if (!j.ok) throw new Error("目录失败");
    models = j.models?.length ? j.models : models;
    setModelsState(`就绪（缓存${j.cache_age_days ?? 0}天）`);
  } catch (e) {
    setModelsState("使用退化清单");
  } finally {
    optionize(el.modelA, models);
    optionize(el.modelB, models);
    optionize(el.judgeModel, models);
    optionize(el.builderModel, models);
    // 常用 judge 默认
    const existsMini = models.find((m) => /4o-mini|mini/i.test(m.id));
    if (existsMini) el.judgeModel.value = existsMini.id;
  }
}
async function refreshModels() {
  setModelsState("刷新中…");
  try {
    const r = await fetch(api("models") + "?refresh=1");
    const j = await r.json();
    if (!j.ok) throw new Error("刷新失败");
    models = j.models;
    optionize(el.modelA, models, el.modelA.value);
    optionize(el.modelB, models, el.modelB.value);
    optionize(el.judgeModel, models, el.judgeModel.value);
    optionize(el.builderModel, models, el.builderModel.value);
    setModelsState("已刷新");
  } catch (e) {
    setModelsState("刷新失败（保留旧列表）");
  }
}

// 配额
async function loadQuota() {
  try {
    const r = await fetch(api("quota"));
    const j = await r.json();
    if (!j.ok) throw new Error();
    pill(el.quota, `配额：${j.left}/${j.limit}（今日）`);
    if (j.left <= 0) {
      el.start.disabled = true;
      toast("今日配额已用尽");
    }
  } catch {
    pill(el.quota, "配额：—");
  }
}

// 预设扩写
async function buildPresets() {
  const seed = el.seed.value.trim();
  if (!seed) { toast("请输入一句设定"); el.seed.focus(); return; }
  const model = el.builderModel.value || "openai/gpt-4o-mini";
  el.btnBuild.disabled = true;
  el.btnBuild.textContent = "生成中…";
  try {
    const r = await fetch(api("preset/expand"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seed, builderModel: model }),
    });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || "生成失败");
    el.presetA.value = j.presetA || "";
    el.presetB.value = j.presetB || "";
    toast("已生成预设，可手动微调");
  } catch (e) {
    toast("预设生成失败：" + e.message);
  } finally {
    el.btnBuild.disabled = false;
    el.btnBuild.textContent = "生成预设";
  }
}

// 聊天渲染 —— 统一单列，A 左 / B 右 / J 居中
// 修改 main.js 中的 addMsg 函数
// 请将原有的 addMsg 函数替换为以下代码：

function addMsg({ side, round, initial = "" }) {
  const msg = document.createElement("div");
  msg.className = "msg " + (side === "A" ? "left" : side === "B" ? "right" : "judge");
  msg.dataset.side = side;
  msg.dataset.round = String(round || 0);

  // 创建消息包装器
  const wrapper = document.createElement("div");
  wrapper.className = "msg-wrapper";

  // 创建头像
  const avatar = document.createElement("div");
  avatar.className = "avatar " + (side === "A" ? "a" : side === "B" ? "b" : "j");
  avatar.textContent = side === "J" ? "J" : side;

  // 创建消息内容区
  const msgContent = document.createElement("div");
  msgContent.className = "msg-content";

  // 创建身份标签
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = side === "A" ? "A 方" : side === "B" ? "B 方" : "裁判";

  // 创建气泡
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  
  // 创建内容和打字指示器
  const content = document.createElement("span");
  content.className = "content";
  content.textContent = initial;
  bubble.appendChild(content);
  
  const typing = document.createElement("span");
  typing.className = "typing";
  typing.textContent = "";
  bubble.appendChild(typing);

  // 组装消息结构
  msgContent.appendChild(who);
  msgContent.appendChild(bubble);

  if (side === "J") {
    // 裁判消息：居中显示，头像在上
    wrapper.appendChild(avatar);
    wrapper.appendChild(msgContent);
  } else {
    // A/B消息：添加头像和内容
    wrapper.appendChild(avatar);
    wrapper.appendChild(msgContent);
  }

  msg.appendChild(wrapper);
  el.chat.appendChild(msg);
  el.chat.scrollTop = el.chat.scrollHeight;
  return msg;
}

function appendDelta(msgEl, delta) {
  if (!delta) return;
  const content = msgEl.querySelector(".content");
  if (content) content.textContent += delta;
  el.chat.scrollTop = el.chat.scrollHeight;
}
function finalizeMsg(msgEl, finalTextIfEmpty = "") {
  const content = msgEl.querySelector(".content");
  if (content && (!content.textContent || !content.textContent.trim())) {
    content.textContent = finalTextIfEmpty || "（无内容）";
  }
  const typing = msgEl.querySelector(".typing");
  if (typing) typing.remove();
  msgEl.querySelector(".bubble")?.classList.add("final");
}

// 流式开始
async function startDuel() {
  clampRounds();
  const topic = el.topic.value.trim();
  if (!topic) { toast("请先填写话题"); el.topic.focus(); return; }

  const payload = {
    topic,
    rounds: parseInt(el.rounds.value || "4", 10),
    modelA: el.modelA.value,
    modelB: el.modelB.value,
    presetA: el.presetA.value.trim(),
    presetB: el.presetB.value.trim(),
    reply_style: el.replyStyle.value,
    sharePersona: el.sharePersona.checked,
    judge: el.judgeOn.checked,
    judgePerRound: el.judgePerRound.checked,
    judgeModel: el.judgeModel.value,
  };

  // UI
  inBattle = true;
  el.start.disabled = true;
  el.stop.disabled = false;
  setBattleState("进行中");
  el.chat.innerHTML = "";

  controller = new AbortController();
  let resp;
  try {
    resp = await fetch(api("stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (e) {
    toast("请求失败：" + e.message);
    stopDuel(true);
    return;
  }
  if (!resp.ok || !resp.body) {
    toast("启动失败（可能配额不足或模型不可用）");
    stopDuel(true);
    return;
  }

  // 名称占位
  let nameA = "—", nameB = "—", nameJ = payload.judge ? "—" : "未启用";

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // 当前轮临时消息
  let current = { A: null, B: null, J: null };
  let firstDelta = { A: false, B: false, J: false };

  function apply(obj) {
    const t = obj.type;

    if (t === "meta") {
      nameA = obj.A || nameA;
      nameB = obj.B || nameB;
      nameJ = obj.judge ? (obj.judgeModel || nameJ) : "未启用";
      // 在聊天里显示一条开场信息
      const sys = addMsg({ side: "J", round: 0, initial: "" });
      appendDelta(sys, `🎯 话题：“${obj.topic}”，回合：${obj.rounds}\nA：${nameA}；B：${nameB}` + (obj.judge ? `；裁判：${nameJ}` : "（无裁判）"));
      finalizeMsg(sys);
      return;
    }

    if (t === "error") {
      const who = obj.side || obj.who || "系统";
      const sys = addMsg({ side: "J", round: obj.round || 0, initial: "" });
      appendDelta(sys, `⚠️ ${who} 出错：${obj.message || "未知错误"}`);
      finalizeMsg(sys);
      return;
    }

    if (t === "chunk" || t === "judge_chunk") {
      const side = t === "chunk" ? obj.side : "J";
      if (!current[side]) current[side] = addMsg({ side, round: obj.round || 0, initial: "" });
      if (obj.delta && obj.delta.length) {
        firstDelta[side] = true;
        appendDelta(current[side], obj.delta);
      }
      return;
    }

    if (t === "turn" || t === "judge_turn" || t === "judge_final") {
      const side = t === "turn" ? obj.side : "J";
      if (!current[side]) current[side] = addMsg({ side, round: obj.round || 0, initial: "" });
      // 如果之前没收到 delta，直接写最终文本（防止空白）
      if (!firstDelta[side]) appendDelta(current[side], (obj.text || "").trim());
      finalizeMsg(current[side]);
      current[side] = null;
      firstDelta[side] = false;
      return;
    }

    if (t === "preset") {
      if (obj.A) el.presetA.value = obj.A;
      if (obj.B) el.presetB.value = obj.B;
      const msg = addMsg({ side: "J", round: 0, initial: "" });
      appendDelta(msg, "🔧 已自动扩写人设（可在设置面板内查看/修改）");
      finalizeMsg(msg);
      return;
    }

    if (t === "end") {
      const ok = addMsg({ side: "J", round: 0, initial: "" });
      appendDelta(ok, "✅ 对战结束");
      finalizeMsg(ok);
      stopDuel(true);
      return;
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        try {
          const obj = JSON.parse(line);
          apply(obj);
        } catch {
          // 忽略非 JSON 行
        }
      }
    }
    // flush
    if (buffer.trim()) {
      try { apply(JSON.parse(buffer.trim())); } catch {}
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      const sys = addMsg({ side: "J", round: 0, initial: "" });
      appendDelta(sys, "⚠️ 流中断：" + e.message);
      finalizeMsg(sys);
    }
  } finally {
    stopDuel(true);
  }
}

function stopDuel(silent = false) {
  if (controller) { try { controller.abort(); } catch {} controller = null; }
  inBattle = false;
  el.start.disabled = false;
  el.stop.disabled = true;
  setBattleState("待机");
  if (!silent) toast("已停止对战");
}

// 绑定
el.refreshModels.addEventListener("click", refreshModels);
el.start.addEventListener("click", startDuel);
el.stop.addEventListener("click", () => stopDuel());
el.btnBuild.addEventListener("click", buildPresets);
el.chips.forEach((c)=>c.addEventListener("click", ()=> el.topic.value = c.dataset.topic));
el.rounds.addEventListener("change", clampRounds);
el.judgeOn.addEventListener("change", ()=>{
  const on = el.judgeOn.checked;
  el.judgeModel.disabled = !on;
  el.judgePerRound.disabled = !on;
});

// 启动
loadModels();
loadQuota();
setBattleState("待机");
el.judgeOn.dispatchEvent(new Event("change"));
