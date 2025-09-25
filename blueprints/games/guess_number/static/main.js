// blueprints/games/guess_number/static/main.js
const $ = (s) => document.querySelector(s);
const log = (t) => { $("#log").insertAdjacentHTML("beforeend", `<div>${t}</div>`); };

// ★ 适配有/无尾斜杠：保证以 / 结尾
const BASE = (()=>{
  const p = window.location.pathname;
  return p.endsWith("/") ? p : p + "/";
})();

// ---- 启动一局（不清空日志） ----
async function start() {
  try {
    const r = await fetch(`${BASE}api/start`, { method: "POST" });
    const j = await r.json();
    if (!j.ok) {
      if (j.error === "DAILY_LIMIT") log("今日次数已用尽");
      else log("启动失败");
    }
  } catch {
    log("网络异常（启动）");
  }
}

// ★ 页面加载就先启动一局，并把这个 Promise 暴露出去，供 guess 等待
const ready = start();

let localTries = 0;
const btn = document.getElementById("btn");

// ---- 绑定事件在 DOMContentLoaded 后 ----
window.addEventListener("DOMContentLoaded", () => {
  // 等待启动完成再允许点击（避免竞态）
  btn.disabled = true;
  ready.finally(() => { btn.disabled = false; });

  btn.addEventListener("click", guess);
  $("#num").addEventListener("keydown", (e) => { if (e.key === "Enter") guess(); });
});

async function guess() {
  // 防止用户在启动未完成时狂点
  await ready;

  const n = +$("#num").value;
  if (!Number.isInteger(n) || n < 1 || n > 100) {
    log("请输入 1~100 的整数");
    return;
  }

  localTries += 1;
  const line = document.createElement("div");
  line.textContent = `第 ${localTries} 次：提交中...`;
  $("#log").appendChild(line);

  try {
    // ★ 用表单编码，避免 CORS 预检（OPTIONS）
    const r = await fetch(`${BASE}api/guess`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ n: String(n) }),
    });

    // 防止服务端异常（如 500/HTML）导致 .json() 报错
    if (!r.ok) {
      line.textContent = `出错了（${r.status}）`;
      return;
    }

    const j = await r.json();

    if (!j.ok) {
      if (j.error === "DAILY_LIMIT")           line.textContent = "今日次数已用尽";
      else if (j.error === "BAD_INPUT")        line.textContent = "输入有误";
      else if (j.error === "BAD_INPUT_RANGE")  line.textContent = "请输入 1~100 的整数";
      else                                     line.textContent = "出错了";
      return;
    }

    line.textContent = j.result === "equal"
      ? `🎉 猜对了！共 ${j.tries} 次`
      : (j.result === "low" ? `小了（第 ${j.tries} 次）` : `大了（第 ${j.tries} 次）`);
  } catch {
    line.textContent = "网络异常";
  }
}
