// static/games/ai_duel/main.js

const BASE = document.body.dataset.base.replace(/\/?$/, "/"); // 确保以 / 结尾
const api = (p) => BASE + "api/" + p.replace(/^\//, "");

// ------- DOM -------
const el = {
  quota: document.getElementById("quota"),
  modelsState: document.getElementById("models-state"),
  battleState: document.getElementById("battle-state"),

  topic: document.getElementById("topic"),
  chips: document.querySelectorAll(".chip"),
  modelA: document.getElementById("modelA"),
  modelB: document.getElementById("modelB"),
  judgeModel: document.getElementById("judge-model"),
  rounds: document.getElementById("rounds"),
  replyStyle: document.getElementById("reply-style"),
  sharePersona: document.getElementById("share-persona"),
  judgeOn: document.getElementById("judge-on"),
  judgePerRound: document.getElementById("judge-per-round"),

  start: document.getElementById("start"),
  stop: document.getElementById("stop"),
  refreshModels: document.getElementById("refresh-models"),

  chatA: document.getElementById("chatA"),
  chatB: document.getElementById("chatB"),
  chatJ: document.getElementById("chatJ"),
  modelAName: document.getElementById("modelA-name"),
  modelBName: document.getElementById("modelB-name"),
  judgeName: document.getElementById("judge-name"),

  drawer: document.getElementById("drawer"),
  openSettings: document.getElementById("open-settings"),
  closeSettings: document.getElementById("close-settings"),
  seed: document.getElementById("seed"),
  builderModel: document.getElementById("builder-model"),
  btnBuild: document.getElementById("btn-build"),
  presetA: document.getElementById("presetA"),
  presetB: document.getElementById("presetB"),

  toast: document.getElementById("toast"),
};

let controller = null; // AbortController
let inBattle = false;
let modelsLoaded = false;
let models = [{ id: "fake/demo", name: "内置演示（无 Key）" }];

// ------- Utils -------
function toast(msg, ms = 2200) {
  el.toast.textContent = msg;
  el.toast.hidden = false;
  setTimeout(() => (el.toast.hidden = true), ms);
}

function pill(elm, text) {
  elm.textContent = text;
}

function setBattleState(s) {
  pill(el.battleState, `状态：${s}`);
}
function setModelsState(s) {
  pill(el.modelsState, `模型目录：${s}`);
}

function optionize(select, list, preferredId = "") {
  const old = select.value;
  select.innerHTML = "";
  list.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.name || m.id;
    select.appendChild(opt);
  });
  // 尝试恢复/预选
  const pick =
    (preferredId && list.find((x) => x.id === preferredId)?.id) ||
    (list.find((x) => /qwen|llama|claude|gpt|gemini|deepseek/i.test(x.id))?.id) ||
    list[0]?.id;
  select.value = old && list.some((x) => x.id === old) ? old : pick || "";
}

function clampRoundsInput() {
  const v = Math.max(1, Math.min(10, parseInt(el.rounds.value || "4", 10)));
  el.rounds.value = String(v);
}

// ------- Models (async, non-blocking) -------
async function loadModelsNonBlocking() {
  try {
    setModelsState("加载中…");
    const resp = await fetch(api("models"));
    const j = await resp.json();
    if (!j.ok) throw new Error("加载失败");
    models = j.models && j.models.length ? j.models : models;
    modelsLoaded = true;
    setModelsState(`就绪（缓存${j.cache_age_days ?? 0}天）`);
  } catch (e) {
    setModelsState("使用退化清单");
  } finally {
    // 填充下拉（包括 builder & judge）
    optionize(el.modelA, models);
    optionize(el.modelB, models);
    optionize(el.judgeModel, models);
    optionize(el.builderModel, models);
    // 默认 judge 开在一个轻量模型上
    if (models.some((m) => m.id.includes("gpt-4o-mini")))
      el.judgeModel.value = "openai/gpt-4o-mini";
  }
}

async function refreshModels() {
  setModelsState("刷新中…");
  try {
    const resp = await fetch(api("models") + "?refresh=1");
    const j = await resp.json();
    if (!j.ok) throw new Error("刷新失败");
    models = j.models;
    optionize(el.modelA, models, el.modelA.value);
    optionize(el.modelB, models, el.modelB.value);
    optionize(el.judgeModel, models, el.judgeModel.value);
    optionize(el.builderModel, models, el.builderModel.value);
    setModelsState("已刷新");
  } catch (e) {
    setModelsState("刷新失败（使用旧缓存）");
  }
}

// ------- Quota -------
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

// ------- Drawer -------
function openDrawer() {
  el.drawer.classList.add("open");
}
function closeDrawer() {
  el.drawer.classList.remove("open");
}

// ------- Chat helpers -------
function addBubble(col, round, who, initial = "") {
  // who: 'A' | 'B' | 'J'
  const wrap = document.createElement("div");
  wrap.className = "bubble";
  wrap.dataset.round = String(round);
  wrap.dataset.who = who;
  wrap.textContent = initial || "";
  const typing = document.createElement("span");
  typing.className = "typing";
  typing.textContent = "…";
  wrap.appendChild(typing);
  col.appendChild(wrap);
  col.scrollTop = col.scrollHeight;
  return wrap;
}
function finalizeBubble(b) {
  b.classList.add("final");
  const t = b.querySelector(".typing");
  if (t) t.remove();
}

function ensureCol(side) {
  return side === "A" ? el.chatA : side === "B" ? el.chatB : el.chatJ;
}

// ------- Streaming -------
async function startDuel() {
  clampRoundsInput();
  const topic = el.topic.value.trim();
  if (!topic) {
    toast("请先填写话题");
    el.topic.focus();
    return;
  }
  const rounds = parseInt(el.rounds.value || "4", 10);
  const payload = {
    topic,
    rounds,
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

  // UI 状态
  inBattle = true;
  el.start.disabled = true;
  el.stop.disabled = false;
  setBattleState("进行中");
  el.chatA.innerHTML = "";
  el.chatB.innerHTML = "";
  el.chatJ.innerHTML = "";
  el.modelAName.textContent = "—";
  el.modelBName.textContent = "—";
  el.judgeName.textContent = payload.judge ? "—" : "未启用";

  // 建立流
  controller = new AbortController();
  const resp = await fetch(api("stream"), {
    method: "POST",
    body: JSON.stringify(payload),
    headers: { "Content-Type": "application/json" },
    signal: controller.signal,
  }).catch((e) => ({ ok: false, error: e.message }));

  if (!resp || !resp.ok || !resp.body) {
    toast("请求失败，请检查网络或配额");
    stopDuel(true);
    return;
  }

  // 解析 NDJSON
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  // 当前轮的气泡缓存：{ A: {...}, B: {...}, J: {...} }
  let current = { A: null, B: null, J: null };
  let firstDelta = { A: false, B: false, J: false };

  function applyEvent(obj) {
    const t = obj.type;
    if (t === "meta") {
      el.modelAName.textContent = obj.A || "—";
      el.modelBName.textContent = obj.B || "—";
      if (obj.judge) el.judgeName.textContent = obj.judgeModel || "—";
      return;
    }
    if (t === "error") {
      const who = obj.side || obj.who || "系统";
      toast(`⚠️ ${who}：${obj.message || "出错"}`, 2800);
      return;
    }
    if (t === "chunk" || t === "judge_chunk") {
      const side = t === "chunk" ? obj.side : "J";
      const col = ensureCol(side);
      if (!current[side]) {
        current[side] = addBubble(col, obj.round || 0, side, "");
      }
      // 有些提供商第一包是空字符串，做个保护：只在首次非空时创建可见文本
      if (obj.delta && obj.delta.length) {
        firstDelta[side] = true;
        current[side].firstChild && (current[side].firstChild.nodeValue += obj.delta);
      }
      return;
    }
    if (t === "turn" || t === "judge_turn" || t === "judge_final") {
      const side = t === "turn" ? obj.side : "J";
      const col = ensureCol(side);
      if (!current[side]) {
        // 异常情况下没有 chunk，直接出 turn
        current[side] = addBubble(col, obj.round || 0, side, "");
      }
      // turn 文本兜底：如果之前没收到任何 delta，则直接写入最终文案，避免“空白回合”
      if (!firstDelta[side]) {
        current[side].firstChild && (current[side].firstChild.nodeValue = (obj.text || "").trim() || "（无内容）");
      }
      finalizeBubble(current[side]);
      current[side] = null;
      firstDelta[side] = false;
      return;
    }
    if (t === "preset") {
      // 收到后端扩写的人设（如果你走 /api/stream 内置扩写）
      if (obj.A) el.presetA.value = obj.A;
      if (obj.B) el.presetB.value = obj.B;
      return;
    }
    if (t === "end") {
      stopDuel();
      return;
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (!line) continue;
        try {
          const obj = JSON.parse(line);
          applyEvent(obj);
        } catch {
          // 略过非 JSON 行
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      toast("流中断：" + e.message);
    }
  } finally {
    stopDuel(true); // 确保按钮状态与状态条复位
  }
}

function stopDuel(silent = false) {
  if (controller) {
    try { controller.abort(); } catch {}
    controller = null;
  }
  if (!silent) toast("已停止对战");
  inBattle = false;
  el.start.disabled = false;
  el.stop.disabled = true;
  setBattleState("待机");
}

// ------- Preset builder -------
async function buildPresets() {
  const seed = el.seed.value.trim();
  if (!seed) {
    toast("请输入一句设定");
    el.seed.focus();
    return;
  }
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
    toast("已生成预设，可手工微调");
  } catch (e) {
    toast("预设生成失败：" + e.message);
  } finally {
    el.btnBuild.disabled = false;
    el.btnBuild.textContent = "生成预设";
  }
}

// ------- Bindings -------
el.openSettings.addEventListener("click", openDrawer);
el.closeSettings.addEventListener("click", closeDrawer);
el.refreshModels.addEventListener("click", refreshModels);
el.start.addEventListener("click", startDuel);
el.stop.addEventListener("click", () => stopDuel());
el.btnBuild.addEventListener("click", buildPresets);
el.judgeOn.addEventListener("change", () => {
  el.judgeModel.disabled = !el.judgeOn.checked;
  el.judgePerRound.disabled = !el.judgeOn.checked;
});
el.chips.forEach((c) => c.addEventListener("click", () => (el.topic.value = c.dataset.topic)));
el.rounds.addEventListener("change", clampRoundsInput);

// ------- Boot -------
loadModelsNonBlocking();
loadQuota();
setBattleState("待机");
el.judgeOn.dispatchEvent(new Event("change"));
