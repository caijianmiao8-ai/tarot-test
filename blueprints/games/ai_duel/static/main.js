const $ = s => document.querySelector(s);
const BASE = (p => p.endsWith("/") ? p : p + "/")(location.pathname);
const logEl = $("#log");
const log = html => { logEl.insertAdjacentHTML("beforeend", `<div class="line">${html}</div>`); logEl.scrollTop = logEl.scrollHeight; };

let aborter = null;
let currentLineEl = null;
let transcript = [];

async function loadModels(){
  const r = await fetch(`${BASE}api/models`);
  const j = await r.json();
  for(const el of [$("#modelA"), $("#modelB")]){
    el.innerHTML = "";
    j.models.forEach(m => el.insertAdjacentHTML("beforeend", `<option value="${m.id}">${m.name}</option>`));
  }
}

function beginLine(side, round){
  const who = side==="A"?"🅰️ A方":side==="B"?"🅱️ B方":"🎓 裁判";
  currentLineEl = document.createElement("div");
  currentLineEl.className = "line";
  currentLineEl.innerHTML = `<b>${who}${round?` · 第 ${round} 回合`:''}</b>：<span class="t"></span>`;
  logEl.appendChild(currentLineEl);
  logEl.scrollTop = logEl.scrollHeight;
}
function appendDelta(delta){
  if(!currentLineEl) return;
  currentLineEl.querySelector(".t").textContent += delta;
}

async function start(){
  $("#start").disabled = true; $("#stop").disabled = false;
  logEl.innerHTML = ""; transcript = []; currentLineEl = null;

  const body = {
    topic:  $("#topic").value.trim(),
    rounds: +$("#rounds").value,
    modelA: $("#modelA").value, stanceA: $("#stanceA").value.trim() || "正方",
    modelB: $("#modelB").value, stanceB: $("#stanceB").value.trim() || "反方",
    judge:  $("#judge").checked
  };
  if(!body.topic){ log("请输入命题"); $("#start").disabled=false; $("#stop").disabled=true; return; }

  aborter = new AbortController();

  try{
    const r = await fetch(`${BASE}api/stream`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body),
      signal: aborter.signal
    });
    if(!r.ok){ log(`出错了（${r.status}）`); return; }

    const reader = r.body.getReader();
    const td = new TextDecoder();
    let buf = "";
    let activeSide = null, activeRound = null;

    while(true){
      const {value, done} = await reader.read();
      if(done) break;
      buf += td.decode(value, {stream:true});

      let idx;
      while((idx = buf.indexOf("\n")) >= 0){
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx+1);
        if(!line) continue;
        let msg; try{ msg = JSON.parse(line); } catch{ continue; }

        if(msg.type==="meta"){
          log(`题目：<b>${msg.topic}</b>（回合：${msg.rounds}）`);
          log(`A：${msg.A} · 立场「${msg.stanceA}」 | B：${msg.B} · 立场「${msg.stanceB}」`);
        }else if(msg.type==="chunk"){
          if(activeSide!==msg.side || activeRound!==msg.round){
            activeSide = msg.side; activeRound = msg.round; beginLine(activeSide, activeRound);
          }
          appendDelta(msg.delta);
        }else if(msg.type==="turn"){
          transcript.push(msg);
          activeSide = null; activeRound = null; currentLineEl = null;
        }else if(msg.type==="judge"){
          beginLine("JUDGE", 0);
          appendDelta(msg.text);
          currentLineEl = null;
        }else if(msg.type==="error"){
          log(`❌ ${msg.side} 第 ${msg.round} 回合出错：${msg.message}`);
        }else if(msg.type==="end"){
          log("<i>对战结束</i>");
        }
      }
    }
  }catch(e){
    log("已停止或网络异常");
  }finally{
    $("#start").disabled = false; $("#stop").disabled = true;

    // 冷路径上报（不阻塞）
    try{
      const data = JSON.stringify({
        topic: $("#topic").value,
        models: {A: $("#modelA").value, B: $("#modelB").value},
        transcript
      });
      navigator.sendBeacon?.(`${BASE}track`, new Blob([data], {type:"application/json"}));
    }catch{}
  }
}

function stop(){
  if(aborter) aborter.abort();
}

window.addEventListener("DOMContentLoaded", async ()=>{
  await loadModels();
  $("#start").addEventListener("click", start);
  $("#stop").addEventListener("click",  stop);
});
