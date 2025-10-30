// blueprints/games/code_playground/static/main.js
//
// 浏览器端控制器：
// - 左侧编辑器监听输入，自动调 /api/compile-preview 拿 {js, css}，更新右侧 iframe
// - 显示编译状态 / 运行期报错
// - 保存当前代码到 localStorage
// - 生成“分享演示”链接 (POST /g/code_playground/snapshot)
// - 左右分栏支持拖拽 + 记忆宽度
//
// 本版：把「几乎所有」Tailwind 兜底逻辑内嵌在 buildPreviewHtml（runtime 规则生成），不依赖其它文件。
// 说明：已支持核心 Utility、任意值类、颜色(全系近似)、斜杠透明度、渐变(from/via/to)、ring、阴影、圆角、尺寸/间距/定位、网格栅格、
//       变体(hover/active/focus/focus-visible/disabled/dark/group-hover/peer-checked)、响应式(sm~2xl)。
//       少量非常规/插件能力（如容器查询、复杂 aria/data 变体）无法 100% 覆盖，遇到具体例子可再扩。

(function () {
  // ---------------------------------------------------------------------------
  // DOM 引用
  // ---------------------------------------------------------------------------
  const editor = document.getElementById("code-editor"); // <textarea>
  const frame = document.getElementById("preview-frame"); // <iframe>
  const overlay = document.getElementById("error-overlay"); // 错误浮层
  const compileBadge = document.getElementById("compile-info"); // “编译成功/失败…”
  const statusLabel = document.getElementById("status-label"); // 顶部状态条
  const buttons = document.querySelectorAll("[data-action]"); // 各种操作按钮
  const compilerRetryButton = document.querySelector(
    '[data-action="reload-compiler"]'
  );

  // ---------------------------------------------------------------------------
  // 常量
  // ---------------------------------------------------------------------------
  const STORAGE_KEY = "code-playground-source";
  const COMPILE_ENDPOINT = "/api/compile-preview";
  const SNAPSHOT_ENDPOINT = "/g/code_playground/snapshot";
  const REQUEST_DEBOUNCE = 320; // ms 防抖

  const DEFAULT_SOURCE = [
    "import React from 'react';",
    "export default function Demo(){",
    "  return (",
    '    <div className="min-h-screen grid place-items-center text-slate-200 bg-gradient-to-br from-slate-900 via-slate-950 to-black font-sans">',
    '      <div className="text-center space-y-4">',
    '        <div className="text-2xl font-semibold">准备就绪</div>',
    '        <div className="text-slate-500 text-sm">你可以在左侧编辑 React + Tailwind 代码</div>',
    "      </div>",
    "    </div>",
    "  );",
    "}",
    "",
  ].join("\n");

  // ---------------------------------------------------------------------------
  // 运行状态
  // ---------------------------------------------------------------------------
  let debounceTimer = null;
  let lastSource = "";
  let currentBlobUrl = null;
  let activeRequestId = 0;
  let currentController = null;

  // ---------------------------------------------------------------------------
  // UI 状态工具
  // ---------------------------------------------------------------------------
  function setStatus(message, state = "idle") {
    const span = statusLabel ? statusLabel.querySelector("span:last-child") : null;
    if (span) span.textContent = message;
    if (statusLabel) statusLabel.dataset.state = state;
  }

  function setCompileInfo(message, good = true) {
    if (!compileBadge) return;
    compileBadge.textContent = message;
    compileBadge.style.background = good ? "rgba(56,189,248,0.18)" : "rgba(248,113,113,0.12)";
    compileBadge.style.color = good ? "#38bdf8" : "#f87171";
    if (compilerRetryButton && good) compilerRetryButton.classList.remove("is-visible");
  }

  function showError(message, labelText = "编译失败") {
    if (overlay) {
      overlay.textContent = message;
      overlay.classList.add("visible");
    }
    setCompileInfo(labelText, false);
    setStatus("出现错误", "error");
    if (compilerRetryButton) compilerRetryButton.classList.add("is-visible");
  }

  function hideError() {
    if (overlay) {
      overlay.textContent = "";
      overlay.classList.remove("visible");
    }
  }

  // iframe runtime 错误监听（iframe 里代码会用 postMessage 回报错）
  window.addEventListener("message", (event) => {
    if (!event || !event.data || event.source !== frame.contentWindow) return;
    if (event.data.type === "CODE_PLAYGROUND_ERROR") {
      showError(event.data.message || "运行时出现错误", "运行时错误");
    }
  });

  // ---------------------------------------------------------------------------
  // 构建 iframe HTML 片段（内嵌 Tailwind 兜底）
  // ---------------------------------------------------------------------------
  function sanitizeScriptContent(js) {
    return (js || "")
      .replace(/<\/script>/gi, "<\\/script>")
      .replace(/<script/gi, "<\\\\script>")
      .replace(/<\/style>/gi, "<\\/style>");
  }

  function buildPreviewHtml(js, css) {
    const script = sanitizeScriptContent(js);
    const styles = css || "";

    // ===== 兜底模块说明 =====
    // 1) tw-fallback-core：最小可用基础（display/flex/grid/spacing/shadow/rounded/text等）
    // 2) tw-fallback-borders：斜杠透明度（white/black）
    // 3) tw-fallback-runtime：重头戏。类名扫描 + 规则生成：
    //    - 解析任意值类：bg-[...]/shadow-[...]/rounded-[...]/text-[...]/p-[...]/m-[...]/w-[...]/h-[...]/inset-[...]/translate-[]/scale-[]/ring-[] 等
    //    - 颜色：全色系（slate/gray/zinc/neutral/stone/red/orange/amber/yellow/lime/green/emerald/teal/cyan/sky/blue/indigo/violet/purple/fuchsia/pink/rose）
    //             + 50..900 等级（HSL 近似曲线映射）+ opacity + 斜杠透明度白/黑
    //    - 渐变：bg-gradient-to-* + from-*/via-*/to-* 组合
    //    - 布局：flex/grid/gap/order/basis/grow/shrink/grid-cols/rows/col-span/row-span
    //    - 尺寸：w/h/min/max/inset/translate/opacity/z-index/border宽度/圆角/阴影/ring
    //    - 排版：font/leading/tracking/align/whitespace/overflow/line-clamp(简化)
    //    - 变体：hover/active/focus/focus-visible/disabled/dark/group-hover/peer-checked
    //    - 响应式：sm/md/lg/xl/2xl -> @media(min-width)
    // 4) tw-fallback-boot：健康检查 + 首次扫描

    return [
      "<!DOCTYPE html>",
      '<html lang="zh-CN">',
      "  <head>",
      '    <meta charset="utf-8" />',
      '    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />',

      '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />',
      '    <link rel="preconnect" href="https://fonts.googleapis.com" />',
      '    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />',

      // Tailwind 服务端生成（可能为空）
      '    <style id="tailwind-bundle">',
      styles,
      "    </style>",

      // 1) 基础兜底（保页面不坍）
      '    <style id="tw-fallback-core">',
      "      *,::before,::after{box-sizing:border-box;border-width:0;border-style:solid;border-color:currentColor}",
      "      html,body{margin:0;padding:0;height:100%}",
      "      #root{height:100%;min-height:100%}",
      "      body{font-family:'Inter',system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;background:transparent;color:inherit;overflow:hidden}",
      "      .hidden{display:none!important}.block{display:block!important}.inline-block{display:inline-block!important}.inline{display:inline!important}",
      "      .flex{display:flex!important}.inline-flex{display:inline-flex!important}.grid{display:grid!important}.place-items-center{place-items:center!important}",
      "      .items-start{align-items:flex-start!important}.items-center{align-items:center!important}.items-end{align-items:flex-end!important}",
      "      .justify-start{justify-content:flex-start!important}.justify-center{justify-content:center!important}.justify-between{justify-content:space-between!important}.justify-end{justify-content:flex-end!important}",
      "      .relative{position:relative!important}.absolute{position:absolute!important}.fixed{position:fixed!important}.sticky{position:sticky!important}",
      "      .w-full{width:100%!important}.h-full{height:100%!important}.min-h-0{min-height:0!important}.min-h-screen{min-height:100vh!important}",
      "      .overflow-hidden{overflow:hidden!important}.overflow-auto{overflow:auto!important}.overscroll-contain{overscroll-behavior:contain!important}",
      "      .rounded{border-radius:.25rem!important}.rounded-md{border-radius:.375rem!important}.rounded-lg{border-radius:.5rem!important}",
      "      .rounded-xl{border-radius:.75rem!important}.rounded-2xl{border-radius:1rem!important}.rounded-3xl{border-radius:1.5rem!important}.rounded-full{border-radius:9999px!important}",
      "      .border{border-width:1px!important}.border-0{border-width:0!important}.border-2{border-width:2px!important}.border-4{border-width:4px!important}.border-8{border-width:8px!important}",
      "      .text-xs{font-size:.75rem!important;line-height:1rem!important}.text-sm{font-size:.875rem!important;line-height:1.25rem!important}",
      "      .text-base{font-size:1rem!important;line-height:1.5rem!important}.text-lg{font-size:1.125rem!important;line-height:1.75rem!important}.text-xl{font-size:1.25rem!important;line-height:1.75rem!important}",
      "      .font-medium{font-weight:500!important}.font-semibold{font-weight:600!important}.font-bold{font-weight:700!important}",
      "      .leading-tight{line-height:1.25!important}.leading-relaxed{line-height:1.625!important}",
      "      .shadow{box-shadow:0 1px 3px rgba(0,0,0,.1),0 1px 2px rgba(0,0,0,.06)!important}",
      "      .shadow-md{box-shadow:0 4px 6px -1px rgba(0,0,0,.1),0 2px 4px -1px rgba(0,0,0,.06)!important}",
      "      .shadow-lg{box-shadow:0 10px 15px -3px rgba(0,0,0,.1),0 4px 6px -2px rgba(0,0,0,.05)!important}",
      "      .shadow-xl{box-shadow:0 20px 25px -5px rgba(0,0,0,.1),0 10px 10px -5px rgba(0,0,0,.04)!important}",
      "      .shadow-2xl{box-shadow:0 25px 50px -12px rgba(0,0,0,.25)!important}",
      "      :root{--tw-0:0;--tw-0_5:.125rem;--tw-1:.25rem;--tw-1_5:.375rem;--tw-2:.5rem;--tw-2_5:.625rem;--tw-3:.75rem;--tw-3_5:.875rem;--tw-4:1rem;--tw-5:1.25rem;--tw-6:1.5rem;--tw-8:2rem;--tw-10:2.5rem;--tw-12:3rem;--tw-16:4rem;--tw-20:5rem;--tw-24:6rem;--tw-32:8rem}",
      "      .p-0{padding:0!important}.px-0{padding-left:0!important;padding-right:0!important}.py-0{padding-top:0!important;padding-bottom:0!important}",
      "      .p-2{padding:var(--tw-2)!important}.px-2{padding-left:var(--tw-2)!important;padding-right:var(--tw-2)!important}.py-2{padding-top:var(--tw-2)!important;padding-bottom:var(--tw-2)!important}",
      "      .p-3{padding:var(--tw-3)!important}.px-3{padding-left:var(--tw-3)!important;padding-right:var(--tw-3)!important}.py-3{padding-top:var(--tw-3)!important;padding-bottom:var(--tw-3)!important}",
      "      .p-4{padding:var(--tw-4)!important}.px-4{padding-left:var(--tw-4)!important;padding-right:var(--tw-4)!important}.py-4{padding-top:var(--tw-4)!important;padding-bottom:var(--tw-4)!important}",
      "      .p-5{padding:var(--tw-5)!important}.p-6{padding:var(--tw-6)!important}.p-8{padding:var(--tw-8)!important}.p-10{padding:var(--tw-10)!important}.p-12{padding:var(--tw-12)!important}",
      "      .m-0{margin:0!important}.mx-auto{margin-left:auto!important;margin-right:auto!important}",
      "      .gap-1{gap:var(--tw-1)!important}.gap-2{gap:var(--tw-2)!important}.gap-3{gap:var(--tw-3)!important}.gap-4{gap:var(--tw-4)!important}.gap-6{gap:var(--tw-6)!important}",
      "      .text-white{color:#fff!important}.text-black{color:#000!important}.bg-white{background:#fff!important}.bg-black{background:#000!important}",
      "      .ring{box-shadow:0 0 0 3px rgba(59,130,246,.5)!important}.ring-1{box-shadow:0 0 0 1px rgba(148,163,184,.35)!important}.ring-2{box-shadow:0 0 0 2px rgba(148,163,184,.35)!important}",
      "      .truncate{overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important}",
      "      .pointer-events-none{pointer-events:none!important}.select-none{-webkit-user-select:none;-moz-user-select:none;user-select:none}",
      "      .backdrop-blur{backdrop-filter:blur(6px)!important}.backdrop-blur-md{backdrop-filter:blur(12px)!important}.backdrop-blur-xl{backdrop-filter:blur(24px)!important}.backdrop-blur-2xl{backdrop-filter:blur(36px)!important}",
      "    </style>",

      // 2) 白/黑 斜杠透明度兜底（防止回落纯黑）
      '    <style id="tw-fallback-borders">',
      "      .border-white\\/5{border-color:rgba(255,255,255,.05)!important}.border-white\\/6{border-color:rgba(255,255,255,.06)!important}",
      "      .border-white\\/10{border-color:rgba(255,255,255,.10)!important}.border-white\\/12{border-color:rgba(255,255,255,.12)!important}.border-white\\/15{border-color:rgba(255,255,255,.15)!important}.border-white\\/18{border-color:rgba(255,255,255,.18)!important}.border-white\\/20{border-color:rgba(255,255,255,.20)!important}",
      "      .border-black\\/5{border-color:rgba(0,0,0,.05)!important}.border-black\\/6{border-color:rgba(0,0,0,.06)!important}.border-black\\/10{border-color:rgba(0,0,0,.10)!important}",
      "      .text-white\\/80{color:rgba(255,255,255,.80)!important}",
      "      .bg-white\\/60{background-color:rgba(255,255,255,.60)!important}.bg-white\\/70{background-color:rgba(255,255,255,.70)!important}.bg-white\\/75{background-color:rgba(255,255,255,.75)!important}.bg-white\\/90{background-color:rgba(255,255,255,.90)!important}",
      "      .bg-black\\/55{background-color:rgba(0,0,0,.55)!important}",
      "    </style>",

      // 3) 运行时动态生成器（大覆盖）
      '    <script id="tw-fallback-runtime">',
      "(function(){",
      "  const esc=(s)=>s.replace(/([!\"#$%&'()*+,./:;<=>?@[\\\\\\]^`{|}~])/g,'\\\\$1').replace(/ /g,'_');",
      "  const ensure=(id)=>{let el=document.getElementById(id);if(!el){el=document.createElement('style');el.id=id;document.head.appendChild(el);}return el;};",
      "  const S=ensure('tw-fallback-generated');",
      "  const done=new Set();",
      "  const toPx=(v)=>/^(?:-?\\d+(?:\\.\\d+)?)(px|rem|em|vh|vw|%)$/.test(v)?v:(/^\\d+(?:\\.\\d+)?$/.test(v)?(v*0.25+'rem'):v);",
      "  const decode=(raw)=>raw.replace(/_/g,' ').replace(/\\$\\[/g,'[').replace(/\\$\\]/g,']');",
      "  const breakpoints={sm:640,md:768,lg:1024,xl:1280,'2xl':1536};",
      "  const paletteHue={slate:215,gray:210,zinc:220,neutral:210,stone:30,red:0,orange:24,amber:38,yellow:48,lime:84,green:146,emerald:156,teal:174,cyan:187,sky:204,blue:217,indigo:231,violet:252,purple:270,fuchsia:292,pink:330,rose:350};",
      "  const shadeMap={50:[0.97,0.97],100:[0.94,0.95],200:[0.87,0.90],300:[0.78,0.85],400:[0.67,0.75],500:[0.58,0.65],600:[0.50,0.55],700:[0.42,0.50],800:[0.30,0.45],900:[0.22,0.40]};",
      "  const satBase={gray:0.08,slate:0.10,zinc:0.09,neutral:0.08,stone:0.12,default:0.60};",
      "  const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));",
      "  const hsl=(h,s,l)=>`hsl(${h} ${clamp(s*100,0,100)}% ${clamp(l*100,0,100)}%)`;",
      "  function colorOf(name,shade){",
      "    if(name==='white') return 'rgb(255 255 255)';",
      "    if(name==='black') return 'rgb(0 0 0)';",
      "    const h = paletteHue[name] ?? paletteHue.gray; const [l,sMul] = shadeMap[shade] || shadeMap[500];",
      "    const s = (satBase[name]??satBase.default)*sMul;",
      "    return hsl(h,s,l);",
      "  }",
      "  // 斜杠透明度白/黑 → rgba",
      "  function whiteBlackAlpha(token){",
      "    let m = token.match(/^(white|black)\\/(\\d{1,3})$/);",
      "    if(m){ const a=clamp(parseInt(m[2],10)/100,0,1); const base=m[1]==='white'?[255,255,255]:[0,0,0]; return `rgba(${base[0]},${base[1]},${base[2]},${a})`; }",
      "    m = token.match(/^(white|black)\\/\\[(0?\\.\\d+|\\d*\\.?\\d+)\\]$/);",
      "    if(m){ const a=clamp(parseFloat(m[2]),0,1); const base=m[1]==='white'?[255,255,255]:[0,0,0]; return `rgba(${base[0]},${base[1]},${base[2]},${a})`; }",
      "    return null;",
      "  }",
      "  // 百分比分数：1/2 1/3 2/3 1/4 ... → 50%, 33.333% 等",
      "  function fractionToPercent(fr){ const m=fr.match(/^(\\d+)\\/(\\d+)$/); if(!m) return null; return (parseInt(m[1],10)/parseInt(m[2],10)*100)+'%'; }",
      "  // 响应式、变体处理",
      "  function buildWrapper(variants){",
      "    let media=null, selPrefix='', selSuffix='';",
      "    variants.forEach(v=>{",
      "      if(breakpoints[v]) media=`@media (min-width:${breakpoints[v]}px)`;",
      "      else if(v==='dark') selPrefix += `.dark `;",
      "      else if(v==='hover') selSuffix += `:hover`;",
      "      else if(v==='active') selSuffix += `:active`;",
      "      else if(v==='focus') selSuffix += `:focus`;",
      "      else if(v==='focus-visible') selSuffix += `:focus-visible`;",
      "      else if(v==='disabled') selSuffix += `:disabled`;",
      "      else if(v==='group-hover') selPrefix += `.group:hover `;",
      "      else if(v==='peer-checked') selPrefix += `.peer:checked ~ `;",
      "    });",
      "    return {media, selPrefix, selSuffix};",
      "  }",
      "  // 生成并注入一条规则",
      "  function putRule(selector, body, media){",
      "    const css = media ? `${media}{${selector}{${body}}}` : `${selector}{${body}}`;",
      "    S.appendChild(document.createTextNode(css));",
      "  }",
      "  // 解析单个 utility（不含变体前缀），返回 {selector, body}",
      "  function genUtility(cls){",
      "    // 任意值类 []",
      "    let m;",
      "    if((m=cls.match(/^bg-\\[(.+)\\]$/))) return {body:`background:${decode(m[1])}!important`};",
      "    if((m=cls.match(/^shadow-\\[(.+)\\]$/))) return {body:`box-shadow:${decode(m[1])}!important`};",
      "    if((m=cls.match(/^rounded-\\[(.+)\\]$/))) return {body:`border-radius:${toPx(decode(m[1]))}!important`};",
      "    if((m=cls.match(/^text-\\[(.+)\\]$/))) return {body:`font-size:${toPx(decode(m[1]))}!important;line-height:1.25!important`};",
      "    if((m=cls.match(/^(p|m)([trblxy]?)-\\[(.+)\\]$/))){",
      "      const a=m[2], v=toPx(decode(m[3]));",
      "      const P={ '':`padding:${v}!important`,'t':`padding-top:${v}!important`,'r':`padding-right:${v}!important`,'b':`padding-bottom:${v}!important`,'l':`padding-left:${v}!important`,'x':`padding-left:${v}!important;padding-right:${v}!important`,'y':`padding-top:${v}!important;padding-bottom:${v}!important`};",
      "      const M={ '':`margin:${v}!important`,'t':`margin-top:${v}!important`,'r':`margin-right:${v}!important`,'b':`margin-bottom:${v}!important`,'l':`margin-left:${v}!important`,'x':`margin-left:${v}!important;margin-right:${v}!important`,'y':`margin-top:${v}!important;margin-bottom:${v}!important`};",
      "      return {body: m[1]==='p'?P[a]:M[a]};",
      "    }",
      "    if((m=cls.match(/^([wh]|min-w|min-h|max-w|max-h|inset|top|right|bottom|left)-\\[(.+)\\]$/))){",
      "      let prop=m[1];",
      "      const val=decode(m[2]);",
      "      const dim=(v)=>{ const frac=fractionToPercent(v); if(frac) return frac; return toPx(v); };",
      "      const map={w:'width',h:'height','min-w':'min-width','min-h':'min-height','max-w':'max-width','max-h':'max-height',inset:'inset',top:'top',right:'right',bottom:'bottom',left:'left'};",
      "      return {body:`${map[prop]}:${dim(val)}!important`};",
      "    }",
      "    if((m=cls.match(/^(translate-[xy]|scale)-\\[(.+)\\]$/))){",
      "      const v=decode(m[2]);",
      "      if(m[1]==='scale') return {body:`transform:scale(${parseFloat(v)}) !important`};",
      "      const ax=m[1]==='translate-x'?'translateX':'translateY';",
      "      const val = fractionToPercent(v) || toPx(v);",
      "      return {body:`transform:${ax}(${val}) !important`};",
      "    }",
      "    if((m=cls.match(/^ring-\\[(.+)\\]$/))) return {body:`box-shadow:0 0 0 2px ${decode(m[1])} !important`};",
      "",
      "    // 颜色 / 不透明度 / 渐变",
      "    if((m=cls.match(/^(text|bg|border|ring)-(white|black)\\/(\\d{1,3})$/))|| (m=cls.match(/^(text|bg|border|ring)-(white|black)\\/\\[(0?\\.\\d+|\\d*\\.?\\d+)\\]$/))){",
      "      const col = whiteBlackAlpha(`${m[2]}/${m[3]}`);",
      "      if(!col) return null; const prop=m[1]==='text'?'color':m[1]==='bg'?'background-color':m[1]==='border'?'border-color':'box-shadow';",
      "      const body = prop==='box-shadow'?`0 0 0 2px ${col}`:col;",
      "      return {body:`${prop}${prop==='box-shadow'?':':''}${body}!important`};",
      "    }",
      "    if((m=cls.match(/^(text|bg|border)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(50|100|200|300|400|500|600|700|800|900)$/))){",
      "      const prop=m[1]==='text'?'color':m[1]==='bg'?'background-color':'border-color';",
      "      const col=colorOf(m[2],parseInt(m[3],10));",
      "      return {body:`${prop}:${col}!important`};",
      "    }",
      "    if((m=cls.match(/^(from|via|to)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(50|100|200|300|400|500|600|700|800|900)$/))){",
      "      const col=colorOf(m[2],parseInt(m[3],10)); const varName={'from':'--tw-gradient-from','via':'--tw-gradient-via','to':'--tw-gradient-to'}[m[1]];",
      "      return {body:`${varName}:${col}!important`};",
      "    }",
      "    if((m=cls.match(/^bg-gradient-to-(t|tr|r|br|b|bl|l|tl)$/))){",
      "      const dirMap={t:'to top',tr:'to top right',r:'to right',br:'to bottom right',b:'to bottom',bl:'to bottom left',l:'to left',tl:'to top left'};",
      "      const dir=dirMap[m[1]]; return {body:`background-image:linear-gradient(${dir}, var(--tw-gradient-from,transparent), var(--tw-gradient-via,transparent), var(--tw-gradient-to,transparent))!important`};",
      "    }",
      "",
      "    // 布局/网格/弹性",
      "    if((m=cls.match(/^grid-cols-(\\d+)$/))) return {body:`grid-template-columns:repeat(${parseInt(m[1],10)},minmax(0,1fr))!important`};",
      "    if((m=cls.match(/^grid-rows-(\\d+)$/))) return {body:`grid-template-rows:repeat(${parseInt(m[1],10)},minmax(0,1fr))!important`};",
      "    if((m=cls.match(/^col-span-(\\d+)$/))) return {body:`grid-column:span ${parseInt(m[1],10)} / span ${parseInt(m[1],10)}!important`};",
      "    if((m=cls.match(/^row-span-(\\d+)$/))) return {body:`grid-row:span ${parseInt(m[1],10)} / span ${parseInt(m[1],10)}!important`};",
      "    if((m=cls.match(/^gap-(\\d+(?:\\.\\d+)?)$/))) return {body:`gap:${(parseFloat(m[1])*0.25)}rem!important`};",
      "    if((m=cls.match(/^basis-(\\d+(?:\\.\\d+)?)$/))) return {body:`flex-basis:${(parseFloat(m[1])*0.25)}rem!important`};",
      "    if(cls==='grow') return {body:'flex-grow:1!important'};",
      "    if(cls==='shrink') return {body:'flex-shrink:1!important'};",
      "    if((m=cls.match(/^order-(\\d+)$/))) return {body:`order:${parseInt(m[1],10)}!important`};",
      "",
      "    // 尺寸/位置（标准刻度）",
      "    if((m=cls.match(/^(p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml)-(\\d+(?:\\.\\d+)?|px)$/))){",
      "      const v = m[2]==='px' ? '1px' : (parseFloat(m[2])*0.25)+'rem';",
      "      const map={ p:['padding'], px:['padding-left','padding-right'], py:['padding-top','padding-bottom'], pt:['padding-top'], pr:['padding-right'], pb:['padding-bottom'], pl:['padding-left'], m:['margin'], mx:['margin-left','margin-right'], my:['margin-top','margin-bottom'], mt:['margin-top'], mr:['margin-right'], mb:['margin-bottom'], ml:['margin-left'] };",
      "      const props=map[m[1]]; return {body:props.map(k=>`${k}:${v}!important`).join(';')};",
      "    }",
      "    if((m=cls.match(/^(w|h)-(\\d+(?:\\.\\d+)?|px|full|screen|auto)$/))){",
      "      let v=m[2];",
      "      if(v==='full') v='100%'; else if(v==='screen') v='100vh'; else if(v==='auto') v='auto'; else v=(v==='px'?'1px':(parseFloat(v)*0.25)+'rem');",
      "      return {body:`${m[1]==='w'?'width':'height'}:${v}!important`};",
      "    }",
      "    if((m=cls.match(/^inset-(\\d+(?:\\.\\d+)?|px|0)$/))){",
      "      const v = m[1]==='0'?'0':(m[1]==='px'?'1px':(parseFloat(m[1])*0.25)+'rem');",
      "      return {body:`top:${v}!important;right:${v}!important;bottom:${v}!important;left:${v}!important`};",
      "    }",
      "    if((m=cls.match(/^(top|right|bottom|left)-(\\d+(?:\\.\\d+)?|px|1\\/2)$/))){",
      "      const v = m[2]==='1/2'?'50%':(m[2]==='px'?'1px':(parseFloat(m[2])*0.25)+'rem');",
      "      return {body:`${m[1]}:${v}!important`};",
      "    }",
      "    if((m=cls.match(/^z-(\\d+)$/))) return {body:`z-index:${parseInt(m[1],10)}!important`};",
      "    if((m=cls.match(/^opacity-(\\d{1,3})$/))) return {body:`opacity:${clamp(parseInt(m[1],10),0,100)/100}!important`};",
      "",
      "    // 边框/圆角/阴影/ring 常规模式",
      "    if((m=cls.match(/^border-(\\d+)$/))) return {body:`border-width:${parseInt(m[1],10)}px!important`};",
      "    if((m=cls.match(/^rounded(-(sm|md|lg|xl|2xl|3xl|full))?$/))){",
      "      const r={undefined:'.25rem',sm:'.125rem',md:'.375rem',lg:'.5rem',xl:'.75rem','2xl':'1rem','3xl':'1.5rem',full:'9999px'}[m[2]]; return {body:`border-radius:${r}!important`};",
      "    }",
      "    if((m=cls.match(/^shadow(-(sm|md|lg|xl|2xl))?$/))){",
      "      const map={undefined:'0 1px 3px rgba(0,0,0,.1),0 1px 2px rgba(0,0,0,.06)',sm:'0 1px 2px 0 rgba(0,0,0,.05)',md:'0 4px 6px -1px rgba(0,0,0,.1),0 2px 4px -1px rgba(0,0,0,.06)',lg:'0 10px 15px -3px rgba(0,0,0,.1),0 4px 6px -2px rgba(0,0,0,.05)',xl:'0 20px 25px -5px rgba(0,0,0,.1),0 10px 10px -5px rgba(0,0,0,.04)','2xl':'0 25px 50px -12px rgba(0,0,0,.25)'};",
      "      return {body:`box-shadow:${map[m[2]]}!important`};",
      "    }",
      "    if((m=cls.match(/^ring(-(0|1|2|4|8))?$/))){",
      "      const w={undefined:3,0:0,1:1,2:2,4:4,8:8}[m[2]]; return {body:`box-shadow:0 0 0 ${w}px rgba(59,130,246,.5)!important`};",
      "    }",
      "    if((m=cls.match(/^ring-(\\d+)$/))) return {body:`box-shadow:0 0 0 ${parseInt(m[1],10)}px rgba(59,130,246,.5)!important`};",
      "",
      "    // 排版",
      "    if((m=cls.match(/^font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)$/))){",
      "      const map={thin:100,extralight:200,light:300,normal:400,medium:500,semibold:600,bold:700,extrabold:800,black:900}; return {body:`font-weight:${map[m[1]]}!important`};",
      "    }",
      "    if((m=cls.match(/^text-(left|center|right|justify)$/))) return {body:`text-align:${m[1]}!important`};",
      "    if((m=cls.match(/^leading-(none|tight|snug|normal|relaxed|loose)$/))){",
      "      const map={none:1,tight:1.25,snug:1.375,normal:1.5,relaxed:1.625,loose:2}; return {body:`line-height:${map[m[1]]}!important`};",
      "    }",
      "    if((m=cls.match(/^tracking-(tighter|tight|normal|wide|wider|widest)$/))){",
      "      const map={tighter:'-0.05em',tight:'-0.025em',normal:'0',wide:'0.025em',wider:'0.05em',widest:'0.1em'}; return {body:`letter-spacing:${map[m[1]]}!important`};",
      "    }",
      "    if((m=cls.match(/^whitespace-(normal|nowrap|pre|pre-line|pre-wrap)$/))) return {body:`white-space:${m[1]}!important`};",
      "    if((m=cls.match(/^overflow-(auto|hidden|visible|scroll)$/))) return {body:`overflow:${m[1]}!important`};",
      "    if((m=cls.match(/^object-(contain|cover|fill|none|scale-down)$/))) return {body:`object-fit:${m[1]}!important`};",
      "",
      "    return null;",
      "  }",
      "  // 处理带变体与响应式：例如 sm:hover:text-blue-500",
      "  function processClass(full){",
      "    if(done.has(full)) return;",
      "    done.add(full);",
      "    const parts = full.split(':');",
      "    const variants = [];",
      "    // 按顺序抽取已知前缀做变体/断点包装，其余拼回去当 utility",
      "    let i=0; while(i<parts.length){",
      "      const p=parts[i];",
      "      if(breakpoints[p]||['hover','active','focus','focus-visible','disabled','dark','group-hover','peer-checked'].includes(p)) { variants.push(p); i++; continue; }",
      "      break;",
      "    }",
      "    const utility = parts.slice(i).join(':');",
      "    const rule = genUtility(utility);",
      "    if(!rule) return;",
      "    const {media, selPrefix, selSuffix} = buildWrapper(variants);",
      "    const selector = `${selPrefix}.${esc(full)}${selSuffix}`;",
      "    putRule(selector, rule.body, media);",
      "  }",
      "  // 扫描 DOM + 监听增量",
      "  function sweep(){",
      "    const set=new Set();",
      "    document.querySelectorAll('*').forEach(el=>{ (el.getAttribute('class')||'').split(/\\s+/).forEach(c=>{ if(c) set.add(c); }); });",
      "    set.forEach(processClass);",
      "  }",
      "  const mo=new MutationObserver(()=>{ requestAnimationFrame(sweep); });",
      "  function boot(){ sweep(); mo.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['class']}); }",
      "  window.__TW_FALLBACK_BOOT=boot;",
      "  window.__TW_FALLBACK_OK=function(){ const p=document.createElement('div'); p.style.position='absolute'; p.style.left='-9999px'; p.className='hidden p-4'; document.body.appendChild(p); const ok=(getComputedStyle(p).display==='none')&&(getComputedStyle(p).paddingLeft!=='0px'); p.remove(); return ok; };",
      "  if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', boot); } else { boot(); }",
      "})();",
      '    </script>',

      // 4) 启动一次检查（不影响你现有逻辑）
      '    <script id="tw-fallback-boot">',
      "      try{",
      "        if(!window.__TW_FALLBACK_OK||!window.__TW_FALLBACK_OK()){ console.log('[tw-fallback] Tailwind 未就绪，启用兜底'); }",
      "        window.__TW_FALLBACK_BOOT && window.__TW_FALLBACK_BOOT();",
      "      }catch(e){}",
      "    </script>",

      // baseline（滚动美化）
      '    <style id="sandbox-baseline">',
      "      .shadow-glass-xl{--tw-shadow:0 40px 120px rgba(15,23,42,0.45);box-shadow:var(--tw-ring-offset-shadow,0 0 #0000),var(--tw-ring-shadow,0 0 #0000),var(--tw-shadow)}",
      "      .cupertino-scroll{height:100%;max-height:100%;overflow-y:auto!important;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:rgba(60,60,67,0.36) transparent}",
      "      .cupertino-scroll::-webkit-scrollbar{width:10px;height:10px}",
      "      .cupertino-scroll::-webkit-scrollbar-track{background:transparent;margin:6px}",
      "      .cupertino-scroll::-webkit-scrollbar-thumb{border-radius:999px;border:3px solid transparent;background-clip:padding-box}",
      "      .cupertino-scroll.cupertino-scroll--light::-webkit-scrollbar-thumb{background-color:rgba(60,60,67,0.28)}",
      "      .cupertino-scroll.cupertino-scroll--light:hover::-webkit-scrollbar-thumb{background-color:rgba(60,60,67,0.45)}",
      "      .cupertino-scroll.cupertino-scroll--dark::-webkit-scrollbar-thumb{background-color:rgba(235,235,245,0.25)}",
      "      .cupertino-scroll.cupertino-scroll--dark:hover::-webkit-scrollbar-thumb{background-color:rgba(235,235,245,0.45)}",
      "      .cupertino-scroll::-webkit-scrollbar-corner{background:transparent}",
      "    </style>",

      "  </head>",
      "  <body>",
      '    <div id="root"></div>',

      // React + ReactDOM
      '    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>',
      '    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>',

      // lucide
      '    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>',

      "    <script>",
      "      (function(){",
      "        var iconSource=null,sample=null;",
      "        if(window.lucide && window.lucide.icons && typeof window.lucide.icons==='object'){",
      "          iconSource='lucide.core'; var keys=Object.keys(window.lucide.icons); sample=keys.slice(0,12);",
      "        }",
      "        console.log('[Preview Sandbox] React ok?',!!window.React,'ReactDOM ok?',!!window.ReactDOM,'Icons?',iconSource,'Sample icons:',sample);",
      "      })();",
      "    </script>",

      // esbuild 产物 IIFE：会在 #root 里 mount 组件
      "    <script>",
      script,
      "    </script>",

      "  </body>",
      "</html>",
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // 把 iframe 内容更新为最新编译结果
  // ---------------------------------------------------------------------------
  function applyPreview(js, css) {
    if (currentBlobUrl) {
      try { URL.revokeObjectURL(currentBlobUrl); } catch (_) {}
      currentBlobUrl = null;
    }
    const html = buildPreviewHtml(js, css);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    currentBlobUrl = url;

    frame.removeAttribute("srcdoc");
    frame.src = url;

    const cleanupTimeout = setTimeout(() => {
      if (currentBlobUrl === url) {
        try { URL.revokeObjectURL(url); currentBlobUrl = null; } catch (_) {}
      }
    }, 10000);

    frame.onload = () => {
      clearTimeout(cleanupTimeout);
      if (currentBlobUrl === url) {
        try { URL.revokeObjectURL(url); currentBlobUrl = null; } catch (_) {}
      }
    };
    frame.onerror = () => {
      clearTimeout(cleanupTimeout);
      try {
        URL.revokeObjectURL(url);
        if (currentBlobUrl === url) currentBlobUrl = null;
      } catch (_) {}
    };
  }

  function handleCompileSuccess(js, css) {
    hideError();
    applyPreview(js, css);
    setCompileInfo("编译成功", true);
    setStatus("实时预览", "idle");
  }

  function handleCompileError(message) {
    showError(message || "编译失败", "编译失败");
  }

  // ---------------------------------------------------------------------------
  // 调用后端 /api/compile-preview
  // ---------------------------------------------------------------------------
  async function requestPreview(source, requestId) {
    if (currentController) currentController.abort();
    const controller = new AbortController();
    currentController = controller;

    setCompileInfo("编译中…", true);
    setStatus("编译中", "running");
    hideError();

    const timeoutId = setTimeout(() => {
      controller.abort();
      if (requestId === activeRequestId) handleCompileError("编译超时（30秒），请检查代码复杂度");
    }, 30000);

    try {
      const response = await fetch(COMPILE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      if (requestId !== activeRequestId || currentController !== controller) return;

      if (!response.ok) {
        let errorMessage = "编译失败";
        try {
          const data = await response.json();
          if (data && data.error) errorMessage = data.error;
        } catch (err) {
          errorMessage = response.statusText || errorMessage;
        }
        handleCompileError(errorMessage);
        return;
      }

      const payload = await response.json();
      if (!payload || typeof payload.js !== "string") {
        handleCompileError("编译服务返回了无效的结果");
        return;
      }

      handleCompileSuccess(payload.js, typeof payload.css === "string" ? payload.css : "");
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === "AbortError") return;
      if (requestId !== activeRequestId || currentController !== controller) return;
      handleCompileError(error.message || "网络异常，请稍后重试");
    } finally {
      if (currentController === controller) currentController = null;
    }
  }

  // ---------------------------------------------------------------------------
  // 调度编译，带防抖
  // ---------------------------------------------------------------------------
  function scheduleUpdate(immediate = false) {
    const source = editor.value;
    if (!immediate && source === lastSource) return;

    const trigger = () => {
      lastSource = source;
      activeRequestId += 1;
      requestPreview(source, activeRequestId);
    };

    if (immediate) { trigger(); return; }
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(trigger, REQUEST_DEBOUNCE);
  }

  // ---------------------------------------------------------------------------
  // 本地存储
  // ---------------------------------------------------------------------------
  function saveToLocalStorage(key, value) {
    try {
      localStorage.setItem(key, value);
      return true;
    } catch (err) {
      console.error("LocalStorage save failed:", err);
      if (err.name === "QuotaExceededError") {
        setStatus("存储空间已满", "error");
        setTimeout(() => setStatus("实时预览", "idle"), 3000);
      }
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // 分享链接逻辑
  // ---------------------------------------------------------------------------
  async function createShareLink() {
    const source = editor.value;
    setStatus("生成分享链接…", "running");
    try {
      const resp = await fetch(SNAPSHOT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
      });
      if (!resp.ok) {
        let msg = "分享失败";
        try { const maybeData = await resp.json(); if (maybeData && maybeData.error) msg = maybeData.error; }
        catch (_) {}
        throw new Error(msg);
      }
      const data = await resp.json();
      const shareUrl = data && data.url ? data.url : null;
      if (!shareUrl) throw new Error("后端未返回分享URL");

      try {
        await navigator.clipboard.writeText(shareUrl);
        alert("分享链接已生成并复制：\n" + shareUrl);
        setStatus("分享链接已复制", "success");
      } catch {
        alert("分享链接已生成：\n" + shareUrl + "\n(复制失败请手动复制)");
        setStatus("分享链接已生成", "success");
      }
      setTimeout(() => setStatus("实时预览", "idle"), 2000);
    } catch (err) {
      console.error(err);
      alert("分享失败：" + (err.message || err));
      setStatus("分享失败", "error");
      setTimeout(() => setStatus("实时预览", "idle"), 2000);
    }
  }

  // ---------------------------------------------------------------------------
  // 分隔条拖拽逻辑
  // ---------------------------------------------------------------------------
  function setupResizableSplit() {
    const leftPane = document.getElementById("pane-left");
    const handle = document.getElementById("split-handle");
    if (!leftPane || !handle) return;

    const SAVED_KEY = "code-playground-left-width";
    const saved = localStorage.getItem(SAVED_KEY);
    if (saved) {
      const px = parseFloat(saved);
      if (!Number.isNaN(px) && px > 0) leftPane.style.flexBasis = px + "px";
    }

    let dragging = false;
    let startX = 0;
    let startWidth = 0;

    function pointerDown(e) {
      dragging = true;
      startX = e.clientX;
      startWidth = leftPane.getBoundingClientRect().width;
      document.body.classList.add("resizing");
      handle.classList.add("dragging");
      window.addEventListener("pointermove", pointerMove);
      window.addEventListener("pointerup", pointerUp);
    }

    function pointerMove(e) {
      if (!dragging) return;
      const dx = e.clientX - startX;
      let newWidth = startWidth + dx;
      const MIN = 260;
      const MAX = window.innerWidth * 0.8;
      if (newWidth < MIN) newWidth = MIN;
      if (newWidth > MAX) newWidth = MAX;
      leftPane.style.flexBasis = newWidth + "px";
      localStorage.setItem(SAVED_KEY, String(newWidth));
    }

    function pointerUp() {
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove("resizing");
      handle.classList.remove("dragging");
      window.removeEventListener("pointermove", pointerMove);
      window.removeEventListener("pointerup", pointerUp);
    }

    handle.addEventListener("pointerdown", pointerDown, { passive: true });
  }

  // ---------------------------------------------------------------------------
  // action 按钮处理
  // ---------------------------------------------------------------------------
  function handleAction(event) {
    const action = event.currentTarget.dataset.action;
    if (action === "share") { createShareLink(); return; }
    if (action === "reset") {
      editor.value = DEFAULT_SOURCE;
      localStorage.removeItem(STORAGE_KEY);
      scheduleUpdate(true);
      return;
    }
    if (action === "copy") {
      navigator.clipboard.writeText(editor.value)
        .then(() => { setStatus("已复制到剪贴板", "success"); setTimeout(() => setStatus("实时预览", "idle"), 1600); })
        .catch(() => { setStatus("复制失败", "error"); });
      return;
    }
    if (action === "format") {
      if (window.js_beautify) {
        const formatted = window.js_beautify(editor.value, { indent_size: 2, max_preserve_newlines: 2, space_in_empty_paren: false });
        editor.value = formatted; scheduleUpdate(true);
      } else {
        setStatus("格式化工具加载中", "running"); setTimeout(() => setStatus("实时预览", "idle"), 1500);
      }
      return;
    }
    if (action === "reload-compiler") { scheduleUpdate(true); return; }
  }

  // ---------------------------------------------------------------------------
  // 初始化
  // ---------------------------------------------------------------------------
  function init() {
    setupResizableSplit();
    const stored = localStorage.getItem(STORAGE_KEY);
    editor.value = stored || DEFAULT_SOURCE;

    editor.addEventListener("input", () => {
      saveToLocalStorage(STORAGE_KEY, editor.value);
      scheduleUpdate();
    });

    buttons.forEach((btn) => btn.addEventListener("click", handleAction));

    setCompileInfo("等待编译…", true);
    setStatus("实时预览", "idle");
    scheduleUpdate(true);
  }

  init();
})();
