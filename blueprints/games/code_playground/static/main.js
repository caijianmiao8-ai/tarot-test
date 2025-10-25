<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>React Playground - Enhanced Edition</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
      background: #0a0a0a; 
      color: #e0e0e0; 
      overflow: hidden;
    }
    
    .container { 
      display: grid; 
      grid-template-columns: 1fr 1fr; 
      height: 100vh; 
      gap: 0;
    }
    
    .editor-panel, .preview-panel { 
      display: flex; 
      flex-direction: column; 
      position: relative;
      background: #1a1a1a;
    }
    
    .panel-header { 
      background: linear-gradient(135deg, #2a2a2a, #1f1f1f); 
      padding: 12px 20px; 
      border-bottom: 1px solid #333;
      display: flex; 
      align-items: center; 
      justify-content: space-between;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    
    .panel-title { 
      font-size: 14px; 
      font-weight: 600; 
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .status-badge {
      padding: 4px 12px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      background: #2563eb;
      color: white;
      transition: all 0.3s;
    }
    
    .status-badge.is-running { background: #f59e0b; animation: pulse 1.5s infinite; }
    .status-badge.is-error { background: #ef4444; }
    .status-badge.is-success { background: #10b981; }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.6; }
    }
    
    .compile-badge {
      padding: 4px 10px;
      border-radius: 8px;
      font-size: 10px;
      background: rgba(59, 130, 246, 0.1);
      color: #60a5fa;
      border: 1px solid rgba(59, 130, 246, 0.2);
    }
    
    .compile-badge.is-compiling {
      animation: pulse 1s infinite;
    }
    
    .toolbar { 
      display: flex; 
      gap: 8px; 
      align-items: center;
    }
    
    .btn { 
      padding: 6px 14px; 
      border: none; 
      border-radius: 8px; 
      font-size: 12px; 
      font-weight: 500;
      cursor: pointer; 
      transition: all 0.2s;
      background: rgba(255,255,255,0.05);
      color: #e0e0e0;
      border: 1px solid rgba(255,255,255,0.1);
    }
    
    .btn:hover { 
      background: rgba(255,255,255,0.1); 
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    
    .btn:active { transform: translateY(0); }
    
    .btn-primary {
      background: linear-gradient(135deg, #3b82f6, #2563eb);
      color: white;
      border: none;
    }
    
    .btn-primary:hover {
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
    }
    
    .btn.is-visible { display: block; }
    .btn:not(.is-visible) { display: none; }
    
    #code-editor { 
      flex: 1; 
      padding: 20px; 
      font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace; 
      font-size: 13px; 
      line-height: 1.6;
      background: #1a1a1a; 
      color: #e0e0e0; 
      border: none; 
      resize: none; 
      outline: none;
      tab-size: 2;
    }
    
    #code-editor::-webkit-scrollbar { width: 12px; }
    #code-editor::-webkit-scrollbar-track { background: #1a1a1a; }
    #code-editor::-webkit-scrollbar-thumb { 
      background: #333; 
      border-radius: 6px;
      border: 2px solid #1a1a1a;
    }
    #code-editor::-webkit-scrollbar-thumb:hover { background: #444; }
    
    .preview-container { 
      flex: 1; 
      position: relative; 
      background: white;
    }
    
    #preview-frame { 
      width: 100%; 
      height: 100%; 
      border: none; 
      background: white;
    }
    
    #error-overlay {
      position: absolute;
      inset: 0;
      background: rgba(0, 0, 0, 0.95);
      padding: 32px;
      overflow: auto;
      display: none;
      backdrop-filter: blur(10px);
    }
    
    #error-overlay pre {
      background: #1a1a1a;
      padding: 20px;
      border-radius: 12px;
      border-left: 4px solid #ef4444;
      font-size: 13px;
      line-height: 1.6;
    }
    
    .feature-badge {
      position: absolute;
      top: 12px;
      right: 12px;
      background: linear-gradient(135deg, #10b981, #059669);
      color: white;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 11px;
      font-weight: 600;
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
      z-index: 10;
      animation: float 3s ease-in-out infinite;
    }
    
    @keyframes float {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-5px); }
    }
    
    @media (max-width: 1024px) {
      .container { 
        grid-template-columns: 1fr; 
        grid-template-rows: 1fr 1fr; 
      }
    }
  </style>
</head>
<body>
  <div class="feature-badge">✨ Enhanced Tailwind Support</div>
  
  <div class="container">
    <!-- 编辑器面板 -->
    <div class="editor-panel">
      <div class="panel-header">
        <div class="panel-title">
          <span>📝</span>
          <span>React Editor</span>
          <span class="compile-badge" id="compile-info">就绪</span>
        </div>
        <div class="toolbar">
          <button class="btn" data-action="format">格式化</button>
          <button class="btn" data-action="copy">复制代码</button>
          <button class="btn" data-action="reset">重置</button>
          <button class="btn btn-primary" data-action="reload-compiler">重试编译器</button>
        </div>
      </div>
      <textarea id="code-editor" spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off"></textarea>
    </div>
    
    <!-- 预览面板 -->
    <div class="preview-panel">
      <div class="panel-header">
        <div class="panel-title">
          <span>👀</span>
          <span>Live Preview</span>
          <span class="status-badge" id="status-label">就绪</span>
        </div>
      </div>
      <div class="preview-container">
        <iframe id="preview-frame" sandbox="allow-scripts allow-same-origin allow-popups"></iframe>
        <div id="error-overlay"></div>
      </div>
    </div>
  </div>

  <!-- 增强版 Playground 脚本 -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/js-beautify/1.14.7/beautify.min.js"></script>
  <script>
(function () {
  const editor = document.getElementById("code-editor");
  const frame = document.getElementById("preview-frame");
  const overlay = document.getElementById("error-overlay");
  const compileBadge = document.getElementById("compile-info");
  const statusLabel = document.getElementById("status-label");
  const buttons = document.querySelectorAll("[data-action]");
  const compilerRetryButton = document.querySelector('[data-action="reload-compiler"]');
  const STORAGE_KEY = "code-playground-source";
  const BABEL_SOURCES = [
    "https://unpkg.com/@babel/standalone@7.23.9/babel.min.js",
    "https://cdn.jsdelivr.net/npm/@babel/standalone@7.23.9/babel.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.9/babel.min.js",
  ];
  const BABEL_ATTEMPT_TIMEOUT = 8000;
  let babelLoadingPromise = null;

  window.addEventListener("message", (event) => {
    if (!event || !event.data || event.source !== frame.contentWindow) {
      return;
    }
    if (event.data.type === "CODE_PLAYGROUND_ERROR") {
      showError(event.data.message || "运行时出现错误", "运行时错误");
    }
  });

  const DEFAULT_SOURCE = `import React, { useState } from 'react';
import { Monitor, Smartphone, Settings, Sun, Moon, Wifi } from 'lucide-react';

export default function App() {
  const [darkMode, setDarkMode] = useState(true);

  return (
    <div className={"min-h-screen transition-all duration-300 " + (darkMode ? "bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950" : "bg-gradient-to-br from-gray-50 via-blue-50/30 to-gray-50")}>
      <div className="p-8">
        {/* 顶部卡片 */}
        <div className={"rounded-3xl p-8 shadow-2xl backdrop-blur-xl border transition-all " + (darkMode ? "bg-slate-900/80 border-slate-800/50 shadow-blue-500/20" : "bg-white/80 border-gray-200/60 shadow-blue-500/10")}>
          <div className="flex items-center justify-between mb-6">
            <h1 className={"text-3xl font-bold " + (darkMode ? "text-white" : "text-slate-900")}>
              🚀 Enhanced Playground
            </h1>
            <button
              onClick={() => setDarkMode(!darkMode)}
              className={"p-3 rounded-xl transition-all duration-300 transform hover:scale-110 active:scale-95 " + (darkMode ? "bg-slate-800 hover:bg-slate-700" : "bg-gray-100 hover:bg-gray-200")}
            >
              {darkMode ? <Sun size={24} className="text-yellow-400" /> : <Moon size={24} className="text-indigo-600" />}
            </button>
          </div>
          
          <p className={"text-lg mb-8 " + (darkMode ? "text-slate-400" : "text-slate-600")}>
            ✨ 现在支持完整的 Tailwind CSS 效果！
          </p>
          
          {/* 功能展示卡片 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { icon: '💫', title: '毛玻璃效果', desc: 'backdrop-blur-xl', color: 'blue' },
              { icon: '🎨', title: '渐变背景', desc: 'gradient-to-br', color: 'purple' },
              { icon: '✨', title: '彩色阴影', desc: 'shadow-blue-500', color: 'green' }
            ].map((item, i) => (
              <div
                key={i}
                className={"rounded-2xl p-6 transition-all duration-300 transform hover:scale-105 hover:-translate-y-2 cursor-pointer " + 
                  (darkMode 
                    ? "bg-slate-800/50 hover:bg-slate-800 border border-slate-700/50 hover:shadow-xl hover:shadow-" + item.color + "-500/30"
                    : "bg-white/50 hover:bg-white border border-gray-200/50 hover:shadow-xl hover:shadow-" + item.color + "-500/20"
                  )
                }
              >
                <div className="text-4xl mb-3">{item.icon}</div>
                <h3 className={"text-lg font-bold mb-2 " + (darkMode ? "text-white" : "text-slate-900")}>{item.title}</h3>
                <code className={"text-sm font-mono px-2 py-1 rounded " + (darkMode ? "bg-slate-900/50 text-blue-400" : "bg-gray-100 text-blue-600")}>
                  {item.desc}
                </code>
              </div>
            ))}
          </div>
          
          {/* 状态指示器 */}
          <div className="mt-8 flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className={"w-3 h-3 rounded-full animate-pulse " + (darkMode ? "bg-green-500" : "bg-green-600")}></div>
              <span className={"text-sm font-medium " + (darkMode ? "text-slate-400" : "text-slate-600")}>Tailwind 增强版已启用</span>
            </div>
            <Wifi size={16} className="text-green-500" />
          </div>
        </div>
      </div>
    </div>
  );
}`;

  const CDN_POLYFILLS = {
    react: "https://unpkg.com/react@18/umd/react.development.js",
    "react-dom": "https://unpkg.com/react-dom@18/umd/react-dom.development.js",
    "lucide-react": "https://unpkg.com/lucide-react@0.379.0/dist/lucide-react.umd.js",
  };
  
  const TAILWIND_CDN_SOURCES = [
    'https://cdn.tailwindcss.com?plugins=forms,typography,aspect-ratio',
    'https://unpkg.com/@tailwindcss/browser@3.4.1?plugins=forms,typography,aspect-ratio',
  ];

  // 精简后的核心 CSS，包含所有关键特性
  const CORE_TAILWIND_CSS = \`/* 🚀 Enhanced Tailwind Core - 支持所有现代特效 */
:root{color-scheme:dark;--tw-bg-opacity:1;--tw-text-opacity:1}*,*::before,*::after{box-sizing:border-box;border:0 solid}body{margin:0;font-family:-apple-system,sans-serif;background:#020617;color:#e2e8f0;line-height:1.5;-webkit-font-smoothing:antialiased}button{cursor:pointer;background:none;border:none}

/* 布局 */
.flex{display:flex!important}.inline-flex{display:inline-flex!important}.grid{display:grid!important}.relative{position:relative!important}.absolute{position:absolute!important}.fixed{position:fixed!important}.inset-0{inset:0!important}.z-10{z-index:10!important}.items-center{align-items:center!important}.justify-between{justify-content:space-between!important}.justify-center{justify-content:center!important}.flex-col{flex-direction:column!important}.gap-2{gap:.5rem!important}.gap-3{gap:.75rem!important}.gap-4{gap:1rem!important}.gap-6{gap:1.5rem!important}.gap-8{gap:2rem!important}.grid-cols-1{grid-template-columns:repeat(1,minmax(0,1fr))!important}.grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))!important}.overflow-hidden{overflow:hidden!important}

/* 间距 */
.p-3{padding:.75rem!important}.p-6{padding:1.5rem!important}.p-8{padding:2rem!important}.px-2{padding-left:.5rem!important;padding-right:.5rem!important}.py-1{padding-top:.25rem!important;padding-bottom:.25rem!important}.mb-2{margin-bottom:.5rem!important}.mb-3{margin-bottom:.75rem!important}.mb-6{margin-bottom:1.5rem!important}.mb-8{margin-bottom:2rem!important}.mt-8{margin-top:2rem!important}

/* 尺寸 */
.w-3{width:.75rem!important}.h-3{height:.75rem!important}.min-h-screen{min-height:100vh!important}

/* 文字 */
.text-sm{font-size:.875rem!important;line-height:1.25rem!important}.text-lg{font-size:1.125rem!important;line-height:1.75rem!important}.text-xl{font-size:1.25rem!important;line-height:1.75rem!important}.text-3xl{font-size:1.875rem!important;line-height:2.25rem!important}.text-4xl{font-size:2.25rem!important}.font-medium{font-weight:500!important}.font-bold{font-weight:700!important}.font-mono{font-family:monospace!important}

/* 颜色 */
.text-white{color:#fff!important}.text-slate-400{color:#94a3b8!important}.text-slate-600{color:#475569!important}.text-slate-900{color:#0f172a!important}.text-blue-400{color:#60a5fa!important}.text-blue-600{color:#2563eb!important}.text-green-500{color:#22c55e!important}.text-indigo-600{color:#4f46e5!important}.text-yellow-400{color:#facc15!important}.bg-white{background:#fff!important}.bg-slate-800{background:#1e293b!important}.bg-slate-900{background:#0f172a!important}.bg-slate-900\\/50{background:rgba(15,23,42,.5)!important}.bg-gray-100{background:#f3f4f6!important}.bg-gray-200{background:#e5e7eb!important}.bg-blue-500{background:#3b82f6!important}

/* 🌟 渐变 */
.bg-gradient-to-br{background-image:linear-gradient(to bottom right,var(--tw-gradient-stops))!important}.from-slate-950{--tw-gradient-from:#020617;--tw-gradient-stops:var(--tw-gradient-from),transparent}.via-slate-900{--tw-gradient-stops:var(--tw-gradient-from),#0f172a,transparent}.to-slate-950{--tw-gradient-to:#020617}.from-gray-50{--tw-gradient-from:#f9fafb;--tw-gradient-stops:var(--tw-gradient-from),transparent}.via-blue-50\\/30{--tw-gradient-stops:var(--tw-gradient-from),rgba(239,246,255,.3),transparent}.to-gray-50{--tw-gradient-to:#f9fafb}

/* 边框 */
.border{border-width:1px!important}.border-slate-700\\/50{border-color:rgba(51,65,85,.5)!important}.border-slate-800\\/50{border-color:rgba(30,41,59,.5)!important}.border-gray-200{border-color:#e5e7eb!important}.border-gray-200\\/50{border-color:rgba(229,231,235,.5)!important}.border-gray-200\\/60{border-color:rgba(229,231,235,.6)!important}.rounded-xl{border-radius:.75rem!important}.rounded-2xl{border-radius:1rem!important}.rounded-3xl{border-radius:1.5rem!important}.rounded-full{border-radius:9999px!important}

/* 💫 阴影 - 关键特性！ */
.shadow-xl{box-shadow:0 20px 25px -5px rgba(0,0,0,.1),0 8px 10px -6px rgba(0,0,0,.1)!important}.shadow-2xl{box-shadow:0 25px 50px -12px rgba(0,0,0,.25)!important}.shadow-blue-500\\/10{box-shadow:0 20px 25px -5px rgba(59,130,246,.1)!important}.shadow-blue-500\\/20{box-shadow:0 20px 25px -5px rgba(59,130,246,.2)!important}.shadow-blue-500\\/30{box-shadow:0 20px 25px -5px rgba(59,130,246,.3)!important}.shadow-green-500\\/20{box-shadow:0 20px 25px -5px rgba(34,197,94,.2)!important}.shadow-purple-500\\/20{box-shadow:0 20px 25px -5px rgba(168,85,247,.2)!important}

/* ✨ 毛玻璃 - 关键特性！ */
.backdrop-blur-xl{backdrop-filter:blur(24px)!important;-webkit-backdrop-filter:blur(24px)!important}.bg-slate-900\\/80{background:rgba(15,23,42,.8)!important}.bg-slate-800\\/50{background:rgba(30,41,59,.5)!important}.bg-white\\/50{background:rgba(255,255,255,.5)!important}.bg-white\\/80{background:rgba(255,255,255,.8)!important}

/* 🎬 过渡动画 */
.transition-all{transition:all .15s cubic-bezier(.4,0,.2,1)!important}.duration-300{transition-duration:.3s!important}.transform{transform:translate(var(--tw-translate-x,0),var(--tw-translate-y,0))!important}.scale-95{transform:scale(.95)!important}.scale-105{transform:scale(1.05)!important}.scale-110{transform:scale(1.1)!important}.-translate-y-2{transform:translateY(-.5rem)!important}

/* 🔄 动画 */
.animate-pulse{animation:pulse 2s cubic-bezier(.4,0,.6,1) infinite!important}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

/* 悬停状态 */
.hover\\:scale-105:hover{transform:scale(1.05)!important}.hover\\:scale-110:hover{transform:scale(1.1)!important}.hover\\:-translate-y-2:hover{transform:translateY(-.5rem)!important}.hover\\:bg-slate-700:hover{background:#334155!important}.hover\\:bg-slate-800:hover{background:#1e293b!important}.hover\\:bg-white:hover{background:#fff!important}.hover\\:shadow-xl:hover{box-shadow:0 20px 25px -5px rgba(0,0,0,.1)!important}.hover\\:shadow-blue-500\\/30:hover{box-shadow:0 20px 25px -5px rgba(59,130,246,.3)!important}.hover\\:shadow-green-500\\/20:hover{box-shadow:0 20px 25px -5px rgba(34,197,94,.2)!important}.hover\\:shadow-purple-500\\/20:hover{box-shadow:0 20px 25px -5px rgba(168,85,247,.2)!important}

/* 激活状态 */
.active\\:scale-95:active{transform:scale(.95)!important}

/* 其他 */
.cursor-pointer{cursor:pointer!important}

/* 响应式 */
@media(min-width:768px){.md\\:grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))!important}}
\`;

  function setStatus(text = "实时预览", state = "idle") {
    if (!statusLabel) return;
    statusLabel.textContent = text;
    statusLabel.classList.remove("is-idle", "is-running", "is-error", "is-success");
    statusLabel.classList.add("is-" + state);
  }

  function setCompileInfo(text, loading = false) {
    if (!compileBadge) return;
    compileBadge.textContent = text;
    compileBadge.classList.toggle("is-compiling", loading);
  }

  function showError(message, title = "编译错误") {
    if (overlay) {
      const pre = overlay.querySelector("pre") || document.createElement("pre");
      pre.textContent = message;
      if (!overlay.querySelector("pre")) {
        const heading = document.createElement("h3");
        heading.textContent = title;
        heading.style.cssText = "color:#f87171;font-size:1.25rem;margin-bottom:1rem";
        overlay.appendChild(heading);
        overlay.appendChild(pre);
      }
      overlay.style.display = "block";
    }
    setCompileInfo("编译失败", false);
    setStatus("编译失败", "error");
  }

  function hideError() {
    if (overlay) overlay.style.display = "none";
  }

  async function loadScript(url, timeout = 8000) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const timer = setTimeout(() => {
        script.remove();
        reject(new Error(\`加载超时: \${url}\`));
      }, timeout);
      script.onload = () => {
        clearTimeout(timer);
        resolve();
      };
      script.onerror = () => {
        clearTimeout(timer);
        script.remove();
        reject(new Error(\`加载失败: \${url}\`));
      };
      script.src = url;
      document.head.appendChild(script);
    });
  }

  async function tryLoadBabel() {
    for (const src of BABEL_SOURCES) {
      try {
        await loadScript(src, BABEL_ATTEMPT_TIMEOUT);
        if (window.Babel) {
          console.log(\`✅ Babel 加载成功: \${src}\`);
          return;
        }
      } catch (err) {
        console.warn(\`⚠️ Babel 加载失败: \${src}\`, err);
      }
    }
    throw new Error("所有 Babel CDN 源均加载失败");
  }

  function ensureBabelLoaded() {
    if (window.Babel) return Promise.resolve();
    if (babelLoadingPromise) return babelLoadingPromise;
    babelLoadingPromise = tryLoadBabel();
    return babelLoadingPromise;
  }

  function buildPreviewHtml(compiledCode) {
    return \`<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Preview</title>
  <script src="\${TAILWIND_CDN_SOURCES[0]}" crossorigin="anonymous"></script>
  <style>\${CORE_TAILWIND_CSS}</style>
  \${Object.entries(CDN_POLYFILLS).map(([, url]) => \`<script src="\${url}" crossorigin></script>\`).join("\\n  ")}
</head>
<body>
<div id="root"></div>
<script>
  function reportError(err) {
    window.parent.postMessage({type:'CODE_PLAYGROUND_ERROR',message:err?.message||String(err)},'*');
  }
  try {
    \${compiledCode}
    const App = exports.default || exports;
    if (!App || typeof App !== 'function') throw new Error('无效的组件导出');
    const root = document.getElementById('root');
    const renderer = window.ReactDOM.createRoot ? window.ReactDOM.createRoot(root) : window.ReactDOM.render;
    renderer.render ? renderer.render(React.createElement(App)) : window.ReactDOM.render(React.createElement(App), root);
  } catch (err) {
    reportError(err);
    document.body.innerHTML = '<pre style="padding:24px;color:#fca5a5;font-family:monospace">' + (err.stack || err.message) + '</pre>';
  }
  window.addEventListener('error', e => reportError(e.error || e.message));
  window.addEventListener('unhandledrejection', e => reportError(e.reason));
</script>
</body>
</html>\`;
  }

  function transpile(source) {
    if (!window.Babel) throw new Error("Babel 尚未加载完成");
    return window.Babel.transform(source, {
      sourceType: "module",
      presets: [["react", { runtime: "classic" }]],
      plugins: ["transform-modules-commonjs", "proposal-class-properties", "proposal-object-rest-spread", "proposal-optional-chaining", "proposal-nullish-coalescing-operator"],
      filename: "App.jsx",
      retainLines: true,
    }).code;
  }

  let debounceTimer = null;
  let lastSource = "";
  let currentBlobUrl = null;

  function handleFrameLoad() {
    setCompileInfo("✨ 预览已更新", false);
    setStatus("实时预览", "idle");
    hideError();
  }
  frame.addEventListener("load", handleFrameLoad);

  window.addEventListener("beforeunload", () => {
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl);
      currentBlobUrl = null;
    }
  });

  async function updatePreview(immediate = false) {
    const source = (editor.value || "").trim();
    if (source === lastSource && !immediate) return;
    hideError();

    try {
      await ensureBabelLoaded();
    } catch (err) {
      console.error(err);
      showError("无法加载 Babel 编译器\\n请检查网络连接或点击\\"重试编译器\\"", "加载失败");
      setStatus("编译器加载失败", "error");
      if (compilerRetryButton) compilerRetryButton.classList.add("is-visible");
      return;
    }

    lastSource = source;
    setCompileInfo("编译中…", true);
    setStatus("编译中", "running");

    try {
      const compiled = transpile(source);
      const html = buildPreviewHtml(compiled);
      if (currentBlobUrl) {
        URL.revokeObjectURL(currentBlobUrl);
        currentBlobUrl = null;
      }
      const blob = new Blob([html], { type: "text/html" });
      currentBlobUrl = URL.createObjectURL(blob);
      frame.removeAttribute("srcdoc");
      frame.src = currentBlobUrl;
    } catch (err) {
      console.error(err);
      showError(err.message);
    }
  }

  function scheduleUpdate(immediate = false) {
    if (immediate) {
      updatePreview(true);
      return;
    }
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => updatePreview(false), 320);
  }

  function handleAction(event) {
    const action = event.currentTarget.dataset.action;
    if (action === "reset") {
      editor.value = DEFAULT_SOURCE;
      localStorage.removeItem(STORAGE_KEY);
      scheduleUpdate(true);
    }
    if (action === "copy") {
      navigator.clipboard.writeText(editor.value).then(() => {
        setStatus("已复制", "success");
        setTimeout(() => setStatus("实时预览"), 1600);
      });
    }
    if (action === "format") {
      if (window.js_beautify) {
        editor.value = window.js_beautify(editor.value, { indent_size: 2, max_preserve_newlines: 2 });
        scheduleUpdate(true);
      }
    }
    if (action === "reload-compiler") {
      setCompileInfo("重新加载中…", true);
      ensureBabelLoaded().then(() => scheduleUpdate(true));
    }
  }

  function init() {
    console.log("🚀 Enhanced Playground 已启动！支持完整 Tailwind 特效！");
    const stored = localStorage.getItem(STORAGE_KEY);
    editor.value = stored || DEFAULT_SOURCE;
    editor.addEventListener("input", () => {
      localStorage.setItem(STORAGE_KEY, editor.value);
      scheduleUpdate();
    });
    buttons.forEach(btn => btn.addEventListener("click", handleAction));
    ensureBabelLoaded().then(() => scheduleUpdate(true));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
  </script>
</body>
</html>