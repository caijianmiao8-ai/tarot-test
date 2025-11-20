const $ = (s) => document.querySelector(s);
const log = (t) => { $("#log").insertAdjacentHTML("beforeend", `<div>${t}</div>`); };

// 兼容 /g/guess_number 与 /g/guess_number/
const BASE = (() => (location.pathname.endsWith("/") ? location.pathname : location.pathname + "/"))();

// 启动一局（不清空日志）
async function start() {
  try {
    const r = await fetch(`${BASE}api/start`, { method: "POST" });
    await r.json().catch(()=>({}));
  } catch {}
}
const ready = start(); // 猜之前等它完成，避免“第一次不显示结果”

let localTries = 0;

window.addEventListener("DOMContentLoaded", () => {
  const btn = $("#btn");
  btn.disabled = true;
  ready.finally(() => { btn.disabled = false; });

  $("#btn").addEventListener("click", guess);
  $("#num").addEventListener("keydown", (e) => { if (e.key === "Enter") guess(); });
});

async function guess() {
  await ready;

  const n = +$("#num").value;
  if (!Number.isInteger(n) || n < 1 || n > 100) { log("请输入 1~100 的整数"); return; }

  localTries += 1;
  const line = document.createElement("div");
  line.textContent = `第 ${localTries} 次：提交中...`;
  $("#log").appendChild(line);

  try {
    // 简单请求，避免预检
    const r = await fetch(`${BASE}api/guess`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ n: String(n) }),
    });
    if (!r.ok) { line.textContent = `出错了（${r.status}）`; return; }

    const j = await r.json();
    if (!j.ok) {
      line.textContent = j.error === "BAD_INPUT_RANGE" ? "请输入 1~100 的整数" : "出错了";
      return;
    }

    line.textContent =
      j.result === "equal" ? `🎉 猜对了！共 ${j.tries} 次` :
      j.result === "low"   ? `小了（第 ${j.tries} 次）` :
                              `大了（第 ${j.tries} 次）`;

    // —— 冷路径上报：不阻塞 UI（浏览器会在空闲时发送）——
    try {
      const data = JSON.stringify({ res: j.result, tries: j.tries });
      const blob = new Blob([data], { type: "application/json" });
      navigator.sendBeacon?.(`${BASE}track`, blob);
    } catch {}
  } catch {
    line.textContent = "网络异常";
  }
}
