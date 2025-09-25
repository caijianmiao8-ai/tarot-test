// static/main.js（只展示需要替换的关键部分）
const $ = (s) => document.querySelector(s);
const log = (t) => { $("#log").insertAdjacentHTML("beforeend", `<div>${t}</div>`); };

// ★ 关键：无论当前是 /g/guess_number 还是 /g/guess_number/，都保证 BASE 以 / 结尾
const BASE = (() => {
  let p = window.location.pathname;
  return p.endsWith("/") ? p : p + "/";
})();

async function start() {
  try {
    const r = await fetch(`${BASE}api/start`, { method: "POST" });
    const j = await r.json();
    if (!j.ok) {
      if (j.error === "DAILY_LIMIT") log("今日次数已用尽");
      else log("启动失败");
    } else {
      $("#log").innerHTML = "";
    }
  } catch {
    log("网络异常");
  }
}

let localTries = 0;

async function guess() {
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
    const r = await fetch(`${BASE}api/guess`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ n: String(n) }),
    });
    const j = await r.json();

    if (!j.ok) {
      if (j.error === "DAILY_LIMIT")          line.textContent = "今日次数已用尽";
      else if (j.error === "BAD_INPUT")       line.textContent = "输入有误";
      else if (j.error === "BAD_INPUT_RANGE") line.textContent = "请输入 1~100 的整数";
      else                                    line.textContent = "出错了";
      return;
    }

    line.textContent = j.result === "equal"
      ? `🎉 猜对了！共 ${j.tries} 次`
      : (j.result === "low" ? `小了（第 ${j.tries} 次）` : `大了（第 ${j.tries} 次）`);
  } catch {
    line.textContent = "网络异常";
  }
}

window.addEventListener("DOMContentLoaded", () => {
  start(); // 可保留；/api/guess 也有兜底自动开局
  $("#btn").addEventListener("click", guess);
  $("#num").addEventListener("keydown", (e) => { if (e.key === "Enter") guess(); });
});
