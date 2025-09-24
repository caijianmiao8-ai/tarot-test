// blueprints/games/guess_number/static/main.js
const $ = (sel)=> document.querySelector(sel);
const log = (t)=> { $("#log").insertAdjacentHTML("beforeend", `<div>${t}</div>`); }

$("#btn").addEventListener("click", async ()=>{
  const n = +$("#num").value;
  const r = await fetch("./api/guess", {
    method:"POST", headers:{ "Content-Type":"application/json" },
    body: JSON.stringify({ n })
  }).then(r=>r.json());
  if(!r.ok){ log("输入不合法"); return; }
  log(r.result === "equal" ? "🎉 猜对了！" : (r.result==="low" ? "小了" : "大了"));
});

// 键盘回车也触发
$("#num").addEventListener("keydown", e=>{
  if(e.key === "Enter") $("#btn").click();
});
