const $ = s => document.querySelector(s);
const log = (html) => { $("#log").insertAdjacentHTML("beforeend", `<div class="line">${html}</div>`); };
const BASE = (p => p.endsWith("/") ? p : p + "/")(location.pathname);

let aborter = null;
let transcript = [];

async function loadModels() {
  const r = await fetch(`${BASE}api/models`);
  const j = await r.json();
  for (const el of [$("#modelA"), $("#modelB")]) {
    el.innerHTML = "";
    j.models.forEach(m => el.insertAdjacentHTML("beforeend", `<option value="${m.id}">${m.name}</option>`));
  }
}

function renderTurn(side, round, text) {
  const who = side === "A" ? "🅰️ A方" : (side === "B" ? "🅱️ B方" : "🎓 裁判");
  log(`<b>${who}${round?` · 第 ${round} 回合`:''}</b>：${text}`);
}

async function start() {
  $("#start").disabled = true;
  $("#stop").disabled = false;
  $("#log").innerHTML = "";
  transcript = [];

  const body = {
    topic:  $("#topic").value.trim(),
    rounds: +$("#rounds").value,
    modelA: $("#modelA").value,
    modelB: $("#modelB").value,
    stanceA: $("#stanceA").value.trim() || "正方",
    stanceB: $("#stanceB").value.trim() || "反方",
    judge:  $("#judge").checked
  };
  if (!body.topic) { log("请输入命题"); $("#start").disabled=false; $("#stop").disabled=true; return; }

  aborter = new AbortController();

  try {
    const r = await fetch(`${BASE}api/stream`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
      signal: aborter.signal
    });
    if (!r.ok) { log(`出错了（${r.status}）`); return; }

    const reader = r.body.getReader();
    const td = new TextDecoder("utf-8");
    let buf = "";

    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += td.decode(value, {stream:true});

      let idx;
      while ((idx = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx+1);
        if (!line) continue;
        let msg; try { msg = JSON.parse(line); } catch { continue; }

        if (msg.type === "meta") {
          log(`题目：<b>${msg.topic}</b>（回合：${msg.rounds}）`);
          log(`A：${msg.A} · 立场「${msg.stanceA}」 | B：${msg.B} · 立场「${msg.stanceB}」`);
        } else if (msg.type === "turn") {
          renderTurn(msg.side, msg.round, msg.text);
          transcript.push(msg);
        } else if (msg.type === "judge") {
          renderTurn("JUDGE", 0, msg.text);
          transcript.push({side:"JUDGE", round:0, text:msg.text});
        } else if (msg.type === "end") {
          log("<i>对战结束</i>");
        }
      }
    }
  } catch (e) {
    log("已停止或网络异常");
  } finally {
    $("#start").disabled = false;
    $("#stop").disabled = true;

    // 冷路径上报（不阻塞）
    try {
      const data = JSON.stringify({
        topic: $("#topic").value, 
        models: {A: $("#modelA").value, B: $("#modelB").value},
        transcript
      });
      navigator.sendBeacon?.(`${BASE}track`, new Blob([data], {type:"application/json"}));
    } catch {}
  }
}

function stop() {
  if (aborter) aborter.abort();
}

window.addEventListener("DOMContentLoaded", async () => {
  await loadModels();
  $("#start").addEventListener("click", start);
  $("#stop").addEventListener("click",  stop);
});
