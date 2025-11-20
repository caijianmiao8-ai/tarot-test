// blueprints/games/code_playground/static/main.js
//
// 浏览器端控制器：
// - 左侧编辑器监听输入，自动调 /api/compile-preview 拿 {js, css}，更新右侧 iframe
// - 显示编译状态 / 运行期报错
// - 保存当前代码到 localStorage
// - 生成“分享演示”链接 (POST /g/code_playground/snapshot)
// - 左右分栏支持拖拽 + 记忆宽度
//
// 增强：注入 Tailwind 运行时兜底（TWRuntime）。仅在 tailwind 样式缺失时启用，尽量复刻常用工具类。

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
  const REQUEST_DEBOUNCE = 320; // ms 防抖，避免每敲一个字就POST一次

  // 默认示例（localStorage 没有时用）
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
    const span = statusLabel
      ? statusLabel.querySelector("span:last-child")
      : null;
    if (span) {
      span.textContent = message;
    }
    if (statusLabel) {
      statusLabel.dataset.state = state;
    }
  }

  function setCompileInfo(message, good = true) {
    if (!compileBadge) return;
    compileBadge.textContent = message;
    compileBadge.style.background = good
      ? "rgba(56,189,248,0.18)"
      : "rgba(248,113,113,0.12)";
    compileBadge.style.color = good ? "#38bdf8" : "#f87171";

    if (compilerRetryButton && good) {
      compilerRetryButton.classList.remove("is-visible");
    }
  }

  function showError(message, labelText = "编译失败") {
    if (overlay) {
      overlay.textContent = message;
      overlay.classList.add("visible");
    }
    setCompileInfo(labelText, false);
    setStatus("出现错误", "error");

    if (compilerRetryButton) {
      compilerRetryButton.classList.add("is-visible");
    }
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
      showError(
        event.data.message || "运行时出现错误",
        "运行时错误"
      );
    }
  });

  // ---------------------------------------------------------------------------
  // 构建 iframe HTML 片段
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

    return [
      "<!DOCTYPE html>",
      '<html lang="zh-CN">',
      "  <head>",
      '    <meta charset="utf-8" />',
      '    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />',

      '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />',
      '    <link rel="preconnect" href="https://fonts.googleapis.com" />',
      '    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />',

      // Tailwind 构建结果（可能为空）
      '    <style id="tailwind-bundle">',
      styles,
      "    </style>",

      // 极简 baseline（不制造任何可见风格；修正默认描边为透明，避免黑边）
      '    <style id="sandbox-baseline">',
      "      html, body { margin:0; padding:0; height:100%; }",
      "      #root { height:100%; min-height:100%; }",
      "      *, ::before, ::after {",
      "        box-sizing:border-box; border-width:0; border-style:solid; border-color:transparent;",
      "      }",
      "      body {",
      "        font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;",
      "        -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;",
      "        background: transparent; color: inherit; overflow: hidden;",
      "      }",
      "      button, input, select, textarea { font: inherit; color: inherit; background: transparent; }",
      "    </style>",

      // ===== Tailwind Runtime（仅在 tailwind 缺失时启用） =====
      "    <script>",
      "    (function TWRuntime(){",
      "      function hasTailwind(){",
      "        var el = document.getElementById('tailwind-bundle');",
      "        if(!el) return false;",
      "        var txt = el.textContent || '';",
      "        if(txt.length > 1200) return true;",
      "        if(/--tw-/.test(txt)) return true;",
      "        if(/\\.container|\\.grid|\\.flex|\\.hidden|\\.block/.test(txt)) return true;",
      "        return false;",
      "      }",
      "      if(hasTailwind()) return; // 已有 tailwind，退出兜底",
      "",
      "      var BREAKPOINTS = { sm:640, md:768, lg:1024, xl:1280, '2xl':1536 };",
      "      var COLOR = {",
      "        white:'#ffffff', black:'#000000',",
      "        slate50:'#f8fafc', slate100:'#f1f5f9', slate200:'#e2e8f0', slate300:'#cbd5e1', slate400:'#94a3b8', slate500:'#64748b', slate600:'#475569', slate700:'#334155', slate800:'#1e293b', slate900:'#0f172a', slate950:'#020617',",
      "        green400:'#4ade80', yellow400:'#facc15', red500:'#ef4444', blue500:'#3b82f6', sky400:'#38bdf8'",
      "      };",
      "",
      "      var SPACE = {",
      "        '0':0,'0.5':2,'1':4,'1.5':6,'2':8,'2.5':10,'3':12,'3.5':14,'4':16,'5':20,'6':24,'7':28,'8':32,'9':36,'10':40,'11':44,'12':48,'14':56,'16':64",
      "      };",
      "",
      "      function cssEscape(s){",
      "        if(window.CSS && CSS.escape) return CSS.escape(s);",
      "        return s.replace(/[^a-zA-Z0-9_-]/g, function(ch){ return '\\\\' + ch; });",
      "      }",
      "",
      "      function hexToRgb(hex){",
      "        hex = hex.replace('#','');",
      "        if(hex.length===3){ hex = hex.split('').map(function(c){return c+c;}).join(''); }",
      "        var r = parseInt(hex.slice(0,2),16), g = parseInt(hex.slice(2,4),16), b = parseInt(hex.slice(4,6),16);",
      "        return [r,g,b];",
      "      }",
      "      function parseColor(name){",
      "        // 支持 bg-white/10、text-slate-500、bg-[#0A84FF]/20 等",
      "        var op = 1; var raw=name; var m=name.match(/^(.*)\\/(\\d{1,3})$/);",
      "        if(m){ name=m[1]; op = Math.max(0, Math.min(1, parseInt(m[2],10)/100)); }",
      "        if(/^\\[#/.test(name)){",
      "          var hex = name.replace(/^\\[(#.*?)\\]$/,'$1');",
      "          var rgb = hexToRgb(hex);",
      "          return 'rgba('+rgb[0]+','+rgb[1]+','+rgb[2]+','+op+')';",
      "        }",
      "        if(/^\\[rgb/.test(name)){",
      "          var v = name.replace(/^\\[(rgb[a]?\\(.*?\\))\\]$/,'$1');",
      "          if(op!==1){",
      "            // 简单替换为 rgba",
      "            var nums = v.replace(/.*?\\((.*?)\\).*/,'$1').split(',').map(function(s){return s.trim();});",
      "            var r=nums[0], g=nums[1], b=nums[2], a=(nums[3]!=null? parseFloat(nums[3]):1)*op;",
      "            return 'rgba('+r+','+g+','+b+','+a+')';",
      "          }",
      "          return v;",
      "        }",
      "        // palette，例如 slate-500",
      "        var mm = name.match(/^([a-z]+)-(\\d{2,3})$/);",
      "        if(mm){",
      "          var key = mm[1]+mm[2];",
      "          if(COLOR[key]){",
      "            var rgb = hexToRgb(COLOR[key]);",
      "            return 'rgba('+rgb[0]+','+rgb[1]+','+rgb[2]+','+op+')';",
      "          }",
      "        }",
      "        if(COLOR[name]){",
      "          var rgb2 = hexToRgb(COLOR[name]);",
      "          return 'rgba('+rgb2[0]+','+rgb2[1]+','+rgb2[2]+','+op+')';",
      "        }",
      "        // 默认直接透传（浏览器自己解析），若含 /opacity 则近似为 0.XX 黑白",
      "        if(op!==1){",
      "          if(name==='white'){ return 'rgba(255,255,255,'+op+')'; }",
      "          if(name==='black'){ return 'rgba(0,0,0,'+op+')'; }",
      "        }",
      "        return name; // 兜底",
      "      }",
      "",
      "      function px(n){ return (typeof n==='number')? (n+'px') : n; }",
      "      function sp(v){ return (SPACE[v]!=null)? (SPACE[v]+'px') : null; }",
      "",
      "      function parseArbitrary(str){ // 例如 [92%] -> 92%, [13px] -> 13px",
      "        var m = str.match(/^\\[(.*)\\]$/);",
      "        return m? m[1] : null;",
      "      }",
      "",
      "      function parseUtility(ut){",
      "        // 返回 {decls:[{prop,val}], extra:{spaceY:... , gradientDir:...}}",
      "        var decls = []; var extra={};",
      "        // display",
      "        if(ut==='block') decls.push(['display','block']);",
      "        else if(ut==='inline') decls.push(['display','inline']);",
      "        else if(ut==='inline-block') decls.push(['display','inline-block']);",
      "        else if(ut==='flex') decls.push(['display','flex']);",
      "        else if(ut==='inline-flex') decls.push(['display','inline-flex']);",
      "        else if(ut==='grid') decls.push(['display','grid']);",
      "        else if(ut==='hidden') decls.push(['display','none']);",
      "",
      "        // flex/grid helpers",
      "        else if(ut==='flex-row') decls.push(['flex-direction','row']);",
      "        else if(ut==='flex-col') decls.push(['flex-direction','column']);",
      "        else if(/^items-/.test(ut)){",
      "          var m = ut.replace('items-','');",
      "          var map={start:'flex-start',center:'center',end:'flex-end',stretch:'stretch',baseline:'baseline'};",
      "          if(map[m]) decls.push(['align-items', map[m]]);",
      "        }",
      "        else if(/^justify-/.test(ut)){",
      "          var m2 = ut.replace('justify-','');",
      "          var map2={start:'flex-start',center:'center',end:'flex-end',between:'space-between',around:'space-around',evenly:'space-evenly'};",
      "          if(map2[m2]) decls.push(['justify-content', map2[m2]]);",
      "        }",
      "        else if(/^place-items-/.test(ut)){",
      "          var m3 = ut.replace('place-items-','');",
      "          var map3={start:'start',center:'center',end:'end',stretch:'stretch'};",
      "          if(map3[m3]) decls.push(['place-items', map3[m3]]);",
      "        }",
      "        else if(/^grid-cols-/.test(ut)){",
      "          var n = parseInt(ut.replace('grid-cols-',''),10);",
      "          if(n>0) decls.push(['grid-template-columns','repeat('+n+', minmax(0,1fr))']);",
      "        }",
      "        else if(/^gap-/.test(ut)){",
      "          var v = ut.replace('gap-',''); var val = sp(v) || parseArbitrary(v) || null;",
      "          if(val) decls.push(['gap', val]);",
      "        }",
      "",
      "        // spacing: p-*, m-*（含 x/y/t/r/b/l）",
      "        else if(/^(p|m)([trblxy]?)-/.test(ut)){",
      "          var mm = ut.match(/^(p|m)([trblxy]?)-(.*)$/);",
      "          var isP = mm[1]==='p'; var dir = mm[2]; var raw = mm[3];",
      "          var val = sp(raw) || parseArbitrary(raw) || null; if(!val) return {decls:[]};",
      "          var propBase = isP? 'padding' : 'margin';",
      "          var props = [];",
      "          if(dir===''){ props=['','-top','-right','-bottom','-left'].map(function(s){return propBase+s;}); }",
      "          else if(dir==='x'){ props=[propBase+'-left', propBase+'-right']; }",
      "          else if(dir==='y'){ props=[propBase+'-top', propBase+'-bottom']; }",
      "          else if(dir==='t'){ props=[propBase+'-top']; }",
      "          else if(dir==='r'){ props=[propBase+'-right']; }",
      "          else if(dir==='b'){ props=[propBase+'-bottom']; }",
      "          else if(dir==='l'){ props=[propBase+'-left']; }",
      "          props.forEach(function(p){ decls.push([p,val]); });",
      "        }",
      "",
      "        // width/height/min/max",
      "        else if(/^w-/.test(ut)){",
      "          var v = ut.slice(2); var val = null;",
      "          if(v==='full') val='100%'; else if(/^\\[/.test(v)) val=parseArbitrary(v);",
      "          else if(SPACE[v]!=null) val=SPACE[v]+'px';",
      "          if(val) decls.push(['width', val]);",
      "        }",
      "        else if(/^h-/.test(ut)){",
      "          var v = ut.slice(2); var val = null;",
      "          if(v==='full') val='100%'; else if(/^\\[/.test(v)) val=parseArbitrary(v);",
      "          else if(SPACE[v]!=null) val=SPACE[v]+'px';",
      "          if(val) decls.push(['height', val]);",
      "        }",
      "        else if(ut==='min-h-screen'){ decls.push(['min-height','100vh']); }",
      "        else if(/^max-w-\\[/.test(ut)){",
      "          var val = parseArbitrary(ut.replace('max-w-','')); if(val) decls.push(['max-width', val]);",
      "        }",
      "",
      "        // typography",
      "        else if(/^text-\\[/.test(ut)){",
      "          var val = parseArbitrary(ut.replace('text-','')); if(val) decls.push(['font-size', val]);",
      "        }",
      "        else if(/^text-/.test(ut)){",
      "          var v = ut.replace('text-','');",
      "          var sizeMap={xs:['.75rem','1rem'], sm:['.875rem','1.25rem'], base:['1rem','1.5rem'], lg:['1.125rem','1.75rem'], xl:['1.25rem','1.75rem'], '2xl':['1.5rem','2rem']};",
      "          if(sizeMap[v]){ decls.push(['font-size',sizeMap[v][0]], ['line-height',sizeMap[v][1]]); }",
      "          else { // color",
      "            var col = parseColor(v); if(col) decls.push(['color', col]);",
      "          }",
      "        }",
      "        else if(/^font-/.test(ut)){",
      "          var m=ut.replace('font-',''); var mp={thin:100,extralight:200,light:300,normal:400,medium:500,semibold:600,bold:700,extrabold:800,black:900};",
      "          if(mp[m]!=null) decls.push(['font-weight', String(mp[m])]);",
      "        }",
      "        else if(ut==='text-center'){ decls.push(['text-align','center']); }",
      "",
      "        // background",
      "        else if(/^bg-\\[/.test(ut)){",
      "          var raw = parseArbitrary(ut.replace('bg-','')); if(raw) decls.push(['background', raw]);",
      "        }",
      "        else if(/^bg-/.test(ut)){",
      "          var v = ut.replace('bg-','');",
      "          if(/^gradient-to-/.test(v)){",
      "            var dir=v.replace('gradient-to-','');",
      "            var map={t:'to top', tr:'to top right', r:'to right', br:'to bottom right', b:'to bottom', bl:'to bottom left', l:'to left', tl:'to top left'};",
      "            extra.gradientDir = map[dir] || 'to bottom';",
      "            // 先放置变量，由 from/via/to 设置",
      "            decls.push(['background-image','linear-gradient('+extra.gradientDir+', var(--tw-from, transparent), var(--tw-via, var(--tw-to, transparent)), var(--tw-to, transparent))']);",
      "          } else {",
      "            var col=parseColor(v); if(col) decls.push(['background-color', col]);",
      "          }",
      "        }",
      "        else if(/^from-/.test(ut)){",
      "          var v = ut.replace('from-',''); var col=parseColor(v); if(col) decls.push(['--tw-from', col]);",
      "        }",
      "        else if(/^via-/.test(ut)){",
      "          var v = ut.replace('via-',''); var col=parseColor(v); if(col) decls.push(['--tw-via', col]);",
      "        }",
      "        else if(/^to-/.test(ut)){",
      "          var v = ut.replace('to-',''); var col=parseColor(v); if(col) decls.push(['--tw-to', col]);",
      "        }",
      "",
      "        // border / radius",
      "        else if(ut==='border'){ decls.push(['border-width','1px']); }",
      "        else if(/^border-\\[/.test(ut)){",
      "          var val=parseArbitrary(ut.replace('border-','')); if(val) decls.push(['border-width', val]);",
      "        }",
      "        else if(/^border-/.test(ut)){",
      "          var v=ut.replace('border-',''); var col=parseColor(v); if(col) decls.push(['border-color', col]);",
      "        }",
      "        else if(/^rounded-\\[/.test(ut)){",
      "          var val=parseArbitrary(ut.replace('rounded-','')); if(val) decls.push(['border-radius', val]);",
      "        }",
      "        else if(/^rounded/.test(ut)){",
      "          var map={none:'0', sm:'.125rem', DEFAULT:'.25rem', md:'.375rem', lg:'.5rem', xl:'.75rem', '2xl':'1rem', '3xl':'1.5rem', full:'9999px'};",
      "          var m=ut.split('-')[1]||'DEFAULT'; if(map[m]) decls.push(['border-radius', map[m]]);",
      "        }",
      "",
      "        // effects",
      "        else if(/^opacity-/.test(ut)){",
      "          var n=parseInt(ut.replace('opacity-',''),10); if(!isNaN(n)) decls.push(['opacity', String(n/100)]);",
      "        }",
      "        else if(ut==='shadow'){ decls.push(['box-shadow','0 1px 3px rgba(0,0,0,.1), 0 1px 2px rgba(0,0,0,.06)']); }",
      "        else if(ut==='shadow-lg'){ decls.push(['box-shadow','0 10px 15px rgba(0,0,0,.1), 0 4px 6px rgba(0,0,0,.05)']); }",
      "        else if(/^shadow-\\[/.test(ut)){",
      "          var val=parseArbitrary(ut.replace('shadow-','')); if(val) decls.push(['box-shadow', val]);",
      "        }",
      "        else if(/^backdrop-blur(?:-(sm|md|lg|xl|2xl))?$/.test(ut)){",
      "          var mm=ut.match(/^backdrop-blur(?:-(sm|md|lg|xl|2xl))?$/);",
      "          var map={sm:'4px', md:'12px', lg:'16px', xl:'24px', '2xl':'40px'}; var amt = mm[1]? map[mm[1]]: '8px';",
      "          decls.push(['backdrop-filter','blur('+amt+')']); decls.push(['-webkit-backdrop-filter','blur('+amt+')']);",
      "        }",
      "",
      "        // overflow",
      "        else if(/^overflow-/.test(ut)){",
      "          var v=ut.replace('overflow-',''); var map={hidden:'hidden', auto:'auto', scroll:'scroll', visible:'visible'};",
      "          if(map[v]) decls.push(['overflow', map[v]]);",
      "        }",
      "",
      "        // position & inset",
      "        else if(['relative','absolute','fixed','sticky'].indexOf(ut)>=0){ decls.push(['position', ut]); }",
      "        else if(ut==='inset-0'){ decls.push(['top','0'],['right','0'],['bottom','0'],['left','0']); }",
      "        else if(/^top-/.test(ut) || /^right-/.test(ut) || /^bottom-/.test(ut) || /^left-/.test(ut)){",
      "          var side=ut.split('-')[0]; var raw=ut.slice(side.length+1); var val=sp(raw)||parseArbitrary(raw); if(val) decls.push([side, val]);",
      "        }",
      "",
      "        // z-index",
      "        else if(/^z-/.test(ut)){",
      "          var v = ut.replace('z-',''); var n = (v==='auto')? 'auto' : parseInt(v,10);",
      "          if(!isNaN(n) || v==='auto') decls.push(['z-index', String(n)]);",
      "        }",
      "",
      "        // object-fit",
      "        else if(/^object-/.test(ut)){",
      "          var v=ut.replace('object-',''); if(['contain','cover','fill','none','scale-down'].indexOf(v)>=0) decls.push(['object-fit',v]);",
      "        }",
      "",
      "        // space-y-*",
      "        else if(/^space-y-/.test(ut)){",
      "          var raw=ut.replace('space-y-',''); var val=sp(raw)||parseArbitrary(raw);",
      "          if(val) extra.spaceY = val;",
      "        }",
      "",
      "        return {decls:decls, extra:extra};",
      "      }",
      "",
      "      function splitVariants(token){",
      "        var parts = token.split(':');",
      "        var utility = parts.pop();",
      "        var variants = parts; // 顺序保留",
      "        return {variants:variants, utility:utility};",
      "      }",
      "",
      "      function buildRule(token){",
      "        var pv = splitVariants(token);",
      "        var parsed = parseUtility(pv.utility);",
      "        var decls = parsed.decls; var extra = parsed.extra || {};",
      "        if(!decls.length && !extra.spaceY) return '';",
      "",
      "        // 选择器：保留原始类名（含变体），转义后加到 :hover/:focus 等伪类上",
      "        var cls = '.' + cssEscape(token);",
      "        var sel = cls;",
      "        var mediaWraps = []; var preSel = ''; var postSel = '';",
      "        pv.variants.forEach(function(v){",
      "          if(v==='hover') postSel += ':hover';",
      "          else if(v==='focus') postSel += ':focus';",
      "          else if(v==='active') postSel += ':active';",
      "          else if(v==='dark') preSel = 'html.dark ' + preSel;",
      "          else if(BREAKPOINTS[v]){ mediaWraps.push('@media (min-width:'+BREAKPOINTS[v]+'px)'); }",
      "        });",
      "        if(preSel) sel = preSel + sel; sel = sel + postSel;",
      "",
      "        function declsToCss(ds){ return ds.map(function(d){ return d[0]+':'+d[1]+';'; }).join(''); }",
      "",
      "        var base = '';",
      "        if(decls.length){ base += sel + '{' + declsToCss(decls) + '}'; }",
      "        if(extra.spaceY){",
      "          base += sel + ' > :not([hidden]) ~ :not([hidden])' + '{ margin-top:'+extra.spaceY+'; }';",
      "        }",
      "",
      "        // 嵌套 media",
      "        if(mediaWraps.length){",
      "          var css = base;",
      "          for(var i=mediaWraps.length-1;i>=0;i--){ css = mediaWraps[i] + '{' + css + '}'; }",
      "          return css;",
      "        }",
      "        return base;",
      "      }",
      "",
      "      // 扫描 DOM classes",
      "      var styleEl = document.createElement('style');",
      "      styleEl.id = 'tw-runtime-styles';",
      "      document.head.appendChild(styleEl);",
      "      var sheet = styleEl.sheet;",
      "",
      "      var emitted = new Set();",
      "      function addRuleCss(css){",
      "        if(!css) return;",
      "        // 简单分割；每个 block 插入",
      "        var blocks = css.match(/[^}]+\\}/g) || [];",
      "        for(var i=0;i<blocks.length;i++){",
      "          var b = blocks[i];",
      "          var key = b.trim();",
      "          if(emitted.has(key)) continue;",
      "          try{ sheet.insertRule(key, sheet.cssRules.length); emitted.add(key); }catch(e){}",
      "        }",
      "      }",
      "",
      "      function processToken(token){",
      "        if(!token || emitted.has(token+'__done')){ return; }",
      "        var css = buildRule(token);",
      "        if(css){ addRuleCss(css); }",
      "        emitted.add(token+'__done');",
      "      }",
      "",
      "      function extractTokens(node){",
      "        if(node.nodeType!==1) return [];",
      "        var cls = node.getAttribute('class');",
      "        if(!cls) return [];",
      "        return cls.split(/\\s+/).filter(Boolean);",
      "      }",
      "",
      "      function walk(root){",
      "        var stack=[root];",
      "        while(stack.length){",
      "          var n = stack.pop();",
      "          if(n.nodeType===1){",
      "            extractTokens(n).forEach(processToken);",
      "            var kids=n.children || [];",
      "            for(var i=0;i<kids.length;i++) stack.push(kids[i]);",
      "          }",
      "        }",
      "      }",
      "",
      "      function scanAll(){ walk(document.body || document.documentElement); }",
      "      scanAll();",
      "",
      "      // 观察后续变更",
      "      var mo = new MutationObserver(function(muts){",
      "        muts.forEach(function(m){",
      "          if(m.type==='attributes' && m.attributeName==='class'){",
      "            processToken((m.target.getAttribute('class')||'').split(/\\s+/).filter(Boolean).join(' '));",
      "            (m.target.getAttribute('class')||'').split(/\\s+/).forEach(processToken);",
      "          }",
      "          if(m.addedNodes && m.addedNodes.length){",
      "            for(var i=0;i<m.addedNodes.length;i++){",
      "              var n=m.addedNodes[i];",
      "              if(n.nodeType===1){",
      "                walk(n);",
      "              }",
      "            }",
      "          }",
      "        });",
      "      });",
      "      mo.observe(document.documentElement, { attributes:true, childList:true, subtree:true, attributeFilter:['class'] });",
      "    })();",
      "    </script>",
      "",
      "  </head>",
      "  <body>",
      '    <div id="root"></div>',
      "",
      // React runtime UMD
      '    <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>',
      '    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>',
      "",
      // lucide runtime UMD (window.lucide.icons)
      '    <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>',
      "",
      // 调试日志（可留可删）
      "    <script>",
      "      (function () {",
      "        var iconSource = null;",
      "        var sample = null;",
      "        if (window.lucide && window.lucide.icons && typeof window.lucide.icons === 'object') {",
      "          iconSource = 'lucide.core';",
      "          var keys = Object.keys(window.lucide.icons);",
      "          sample = keys.slice(0, 12);",
      "        }",
      "        console.log('[Preview Sandbox] React ok?', !!window.React, 'ReactDOM ok?', !!window.ReactDOM, 'Icons?', iconSource, 'Sample icons:', sample);",
      "      })();",
      "    </script>",
      "",
      // esbuild 产物 IIFE：会在 #root 里 mount 组件
      "    <script>",
      script,
      "    </script>",
      "",
      "  </body>",
      "</html>",
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // 把 iframe 内容更新为最新编译结果
  // ---------------------------------------------------------------------------
  function applyPreview(js, css) {
    if (currentBlobUrl) {
      try {
        URL.revokeObjectURL(currentBlobUrl);
      } catch (err) {}
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
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (err) {}
      }
    }, 10000);

    frame.onload = () => {
      clearTimeout(cleanupTimeout);
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (err) {}
      }
    };

    frame.onerror = () => {
      clearTimeout(cleanupTimeout);
      try {
        URL.revokeObjectURL(url);
        if (currentBlobUrl === url) {
          currentBlobUrl = null;
        }
      } catch (err) {}
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
    if (currentController) {
      currentController.abort();
    }
    const controller = new AbortController();
    currentController = controller;

    setCompileInfo("编译中…", true);
    setStatus("编译中", "running");
    hideError();

    const timeoutId = setTimeout(() => {
      controller.abort();
      if (requestId === activeRequestId) {
        handleCompileError("编译超时（30秒），请检查代码复杂度");
      }
    }, 30000);

    try {
      const response = await fetch(COMPILE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (requestId !== activeRequestId || currentController !== controller) {
        return;
      }

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

      handleCompileSuccess(
        payload.js,
        typeof payload.css === "string" ? payload.css : ""
      );
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === "AbortError") return;
      if (requestId !== activeRequestId || currentController !== controller) return;
      handleCompileError(error.message || "网络异常，请稍后重试");
    } finally {
      if (currentController === controller) {
        currentController = null;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 调度编译，带防抖
  // ---------------------------------------------------------------------------
  function scheduleUpdate(immediate = false) {
    const source = editor.value;
    if (!immediate && source === lastSource) {
      return;
    }
    const trigger = () => {
      lastSource = source;
      activeRequestId += 1;
      requestPreview(source, activeRequestId);
    };
    if (immediate) {
      trigger();
      return;
    }
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(() => {
      trigger();
    }, REQUEST_DEBOUNCE);
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
  // 分享链接逻辑：上传当前代码，后端返回只读预览的 URL
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
        try {
          const maybeData = await resp.json();
          if (maybeData && maybeData.error) msg = maybeData.error;
        } catch (_) {}
        throw new Error(msg);
      }

      const data = await resp.json();
      const shareUrl = data && data.url ? data.url : null;
      if (!shareUrl) throw new Error("后端未返回分享URL");

      try {
        await navigator.clipboard.writeText(shareUrl);
        alert("分享链接已生成并复制：\n" + shareUrl);
        setStatus("分享链接已复制", "success");
      } catch (copyErr) {
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
  // 分隔条拖拽逻辑：左栏宽度可调并写入 localStorage
  // ---------------------------------------------------------------------------
  function setupResizableSplit() {
    const leftPane = document.getElementById("pane-left");
    const handle = document.getElementById("split-handle");

    if (!leftPane || !handle) return;

    const SAVED_KEY = "code-playground-left-width";
       const saved = localStorage.getItem(SAVED_KEY);
    if (saved) {
      const px = parseFloat(saved);
      if (!Number.isNaN(px) && px > 0) {
        leftPane.style.flexBasis = px + "px";
      }
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
  // action 按钮处理：reset / copy / format / share / reload-compiler
  // ---------------------------------------------------------------------------
  function handleAction(event) {
    const action = event.currentTarget.dataset.action;

    if (action === "share") {
      createShareLink();
      return;
    }

    if (action === "reset") {
      editor.value = DEFAULT_SOURCE;
      localStorage.removeItem(STORAGE_KEY);
      scheduleUpdate(true);
      return;
    }

    if (action === "copy") {
      navigator.clipboard
        .writeText(editor.value)
        .then(() => {
          setStatus("已复制到剪贴板", "success");
          setTimeout(() => setStatus("实时预览", "idle"), 1600);
        })
        .catch(() => {
          setStatus("复制失败", "error");
        });
      return;
    }

    if (action === "format") {
      if (window.js_beautify) {
        const formatted = window.js_beautify(editor.value, {
          indent_size: 2,
          max_preserve_newlines: 2,
          space_in_empty_paren: false,
        });
        editor.value = formatted;
        scheduleUpdate(true);
      } else {
        setStatus("格式化工具加载中", "running");
        setTimeout(() => setStatus("实时预览", "idle"), 1500);
      }
      return;
    }

    if (action === "reload-compiler") {
      scheduleUpdate(true);
      return;
    }
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
