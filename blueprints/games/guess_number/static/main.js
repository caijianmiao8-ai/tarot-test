// static/main.js
const $ = (s)=> document.querySelector(s);
const log = (t)=> { $("#log").insertAdjacentHTML("beforeend", `<div>${t}</div>`); };

async function start() {
  const r = await fetch("./api/start", { method: "POST" });
  const j = await r.json();
  if (!j.ok) {
    if (j.error === "DAILY_LIMIT") {
      log("今日次数已用尽");
    } else {
      log("启动失败");
    }
    throw new Error("start failed");
  }
  $("#log").innerHTML = "";
}

async function guess() {
  const n = +$("#num").value;
  if (!Number.isInteger(n) || n < 1 || n > 100) {
    log("请输入 1~100 的整数");
    return;
  }
  const r = await fetch("./api/guess", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ n })
  });
  const j = await r.json();
  if (!j.ok) {
    if (j.error === "DAILY_LIMIT") log("今日次数已用尽");
    else if (j.error === "BAD_INPUT") log("输入有误");
    else log("出错了");
    return;
  }
  if (j.result === "equal")  log(`🎉 猜对了！共 ${j.tries} 次`);
  if (j.result === "low")    log(`小了（第 ${j.tries} 次）`);
  if (j.result === "high")   log(`大了（第 ${j.tries} 次）`);
}

// 页面加载就开一局（失败也不影响继续猜；/api/guess 会兜底）
start().catch(()=>{});

$("#btn").addEventListener("click", guess);
$("#num").addEventListener("keydown", (e)=>{
  if (e.key === "Enter") guess();
});
