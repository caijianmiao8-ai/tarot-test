(function () {
  const editor = document.getElementById("code-editor");
  const frame = document.getElementById("preview-frame");
  const overlay = document.getElementById("error-overlay");
  const compileBadge = document.getElementById("compile-info");
  const statusLabel = document.getElementById("status-label");
  const buttons = document.querySelectorAll("[data-action]");
  const STORAGE_KEY = "code-playground-source";
  let babelRetryTimer = null;
  let pendingInitialRender = false;

  window.addEventListener("message", (event) => {
    if (!event || !event.data || event.source !== frame.contentWindow) {
      return;
    }
    if (event.data.type === "CODE_PLAYGROUND_ERROR") {
      showError(event.data.message || "运行时出现错误", "运行时错误");
    }
  });

  const DEFAULT_SOURCE = `import React, { useState } from 'react';
import { Monitor, Smartphone, Settings, Sun, Moon, Wifi, Gamepad2 } from 'lucide-react';

const devices = [
  { id: 1, name: '我的工作电脑', delay: '5ms', status: 'online' },
  { id: 2, name: '家里的 MacBook', delay: '12ms', status: 'online' },
  { id: 3, name: 'Linux 服务器', delay: '-', status: 'offline' }
];

export default function RemoteDesktopDemo() {
  const [darkMode, setDarkMode] = useState(false);
  const [selected, setSelected] = useState(devices[0]);

  const theme = darkMode
    ? { bg: 'from-slate-900 via-slate-950 to-black', text: 'text-slate-100', card: 'bg-slate-900/70 border-slate-700/60', badge: 'bg-emerald-400/15 text-emerald-300' }
    : { bg: 'from-sky-100 via-white to-zinc-50', text: 'text-slate-900', card: 'bg-white/80 border-slate-200/70', badge: 'bg-emerald-500/10 text-emerald-600' };

  return (
    <div className={"min-h-screen font-sans transition-colors duration-300 bg-gradient-to-br " + theme.bg}>
      <header className="px-10 py-8 flex items-center justify-between">
        <div>
          <h1 className={"text-3xl font-semibold " + theme.text}>RemoteDesktop</h1>
          <p className="text-slate-500 mt-1">实时远程桌面体验</p>
        </div>
        <button
          onClick={() => setDarkMode(!darkMode)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-900/10 hover:bg-slate-900/20 text-sm"
        >
          {darkMode ? <Sun size={18} /> : <Moon size={18} />}
          {darkMode ? '浅色模式' : '深色模式'}
        </button>
      </header>

      <main className="px-10 pb-10 grid gap-6 lg:grid-cols-[320px_1fr]">
        <aside className={"rounded-3xl border shadow-xl p-6 space-y-4 " + theme.card}>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">设备列表</h2>
            <span className={"text-xs px-2 py-1 rounded-full " + theme.badge}>
              <Wifi size={12} className="inline mr-1" />{devices.filter(d => d.status === 'online').length} 在线
            </span>
          </div>
          <div className="space-y-3">
            {devices.map(device => (
              <button
                key={device.id}
                onClick={() => setSelected(device)}
                className={"w-full text-left px-4 py-3 rounded-2xl transition-all border " +
                  (selected.id === device.id ? 'border-sky-400 bg-sky-400/10 text-sky-200' : 'border-transparent hover:bg-slate-900/5')}
              >
                <div className="flex items-center justify-between">
                  <p className="font-medium">{device.name}</p>
                  <span className="text-xs font-mono">{device.delay}</span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {device.status === 'online' ? '在线 - 极速通道' : '离线 - 等待激活'}
                </p>
              </button>
            ))}
          </div>
          <button className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-sky-500 hover:bg-sky-600 text-white transition">
            <Smartphone size={18} /> 手机远程控制
          </button>
        </aside>

        <section className={"rounded-3xl border shadow-2xl p-8 relative overflow-hidden " + theme.card}>
          <div className="absolute inset-0 bg-gradient-to-br from-sky-500/10 via-transparent to-purple-500/10" aria-hidden="true"></div>
          <div className="relative z-10">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-slate-400">当前连接</p>
                <h2 className={"mt-1 text-2xl font-semibold " + theme.text}>{selected.name}</h2>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/15 text-emerald-300">
                  <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></span>
                  <span className="text-xs font-medium">稳定连接</span>
                </div>
                <button className="px-3 py-1.5 rounded-full bg-slate-900/20 hover:bg-slate-900/30 text-xs">
                  <Settings size={14} />
                </button>
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-3">
              <div className="rounded-2xl bg-slate-900/20 p-4 border border-slate-900/30">
                <p className="text-xs text-slate-400">延迟</p>
                <p className="mt-1 text-3xl font-semibold text-sky-300">{selected.delay}</p>
              </div>
              <div className="rounded-2xl bg-slate-900/20 p-4 border border-slate-900/30">
                <p className="text-xs text-slate-400">帧率</p>
                <p className="mt-1 text-3xl font-semibold text-sky-300">60fps</p>
              </div>
              <div className="rounded-2xl bg-slate-900/20 p-4 border border-slate-900/30">
                <p className="text-xs text-slate-400">控制模式</p>
                <p className="mt-1 text-lg flex items-center gap-2 text-sky-200">
                  <Gamepad2 size={18} /> 键鼠 + 手柄
                </p>
              </div>
            </div>

            <div className="mt-8 h-[360px] rounded-3xl bg-slate-950/60 border border-slate-800/60 p-6">
              <div className="flex items-center gap-3 text-slate-400 text-xs">
                <Monitor size={16} />
                <span>实时画布</span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-300">低延迟模式</span>
              </div>
              <div className="mt-4 h-[280px] rounded-2xl bg-slate-900/80 border border-slate-800/70 flex items-center justify-center">
                <p className="text-slate-500 text-sm">在这里渲染你自定义的 UI 或可视化效果</p>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
`;

  const CDN_POLYFILLS = {
    react: `https://unpkg.com/react@18/umd/react.development.js`,
    "react-dom": `https://unpkg.com/react-dom@18/umd/react-dom.development.js`,
    "lucide-react": `https://unpkg.com/lucide-react@0.379.0/dist/lucide-react.umd.js`,
  };

  function setStatus(message, state = "idle") {
    const span = statusLabel.querySelector("span:last-child");
    span.textContent = message;
    statusLabel.dataset.state = state;
  }

  function setCompileInfo(message, good = true) {
    compileBadge.textContent = message;
    compileBadge.style.background = good ? "rgba(56,189,248,0.18)" : "rgba(248,113,113,0.12)";
    compileBadge.style.color = good ? "#38bdf8" : "#f87171";
  }

  function showError(message, label = "编译失败") {
    overlay.textContent = message;
    overlay.classList.add("visible");
    setCompileInfo(label, false);
    setStatus("出现错误", "error");
  }

  function hideError() {
    overlay.textContent = "";
    overlay.classList.remove("visible");
  }

  function isBabelReady() {
    return Boolean(window.Babel && typeof window.Babel.transform === "function");
  }

  function waitForBabel(callback, attempt = 0) {
    if (isBabelReady()) {
      if (babelRetryTimer) {
        clearTimeout(babelRetryTimer);
        babelRetryTimer = null;
      }
      callback();
      return;
    }

    const delay = Math.min(600, 120 + attempt * 80);
    if (!babelRetryTimer) {
      setCompileInfo("等待编译器…", true);
      setStatus("等待 Babel 编译器", "running");
    }

    babelRetryTimer = setTimeout(() => {
      babelRetryTimer = null;
      waitForBabel(callback, attempt + 1);
    }, delay);
  }

  function normalizeSource(source) {
    return source.replace(/\t/g, "  ");
  }

  function buildPreviewHtml(compiledCode) {
    const encodedCode = JSON.stringify(compiledCode);
    const polyfills = Object.entries(CDN_POLYFILLS)
      .map(([_, url]) => `<script crossorigin src="${url}"></script>`)
      .join("\n");

    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font-family: 'Inter', system-ui, sans-serif; background: #020617; color: #e2e8f0; }
  #preview-root { width: 100vw; height: 100vh; overflow: hidden; }
  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.2); border-radius: 999px; }
</style>
${polyfills}
<script>
  window.ReactDOMClient = window.ReactDOM;
  if (!window.ReactDOMClient.createRoot) {
    window.ReactDOMClient = {
      createRoot: function (el) {
        return {
          render: function (element) {
            return window.ReactDOM.render(element, el);
          }
        };
      }
    };
  }
  window.lucideReact = window.lucideReact || window.lucide;
  if (!window.lucideReact) {
    const fallback = new Proxy({}, {
      get: function () {
        return function IconStub(props) {
          const size = props?.size || 16;
          return window.React.createElement('span', {
            style: {
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: size,
              height: size,
              borderRadius: '50%',
              background: 'rgba(148,163,184,0.18)',
              color: '#94a3b8',
              fontSize: size * 0.5,
              fontWeight: 600,
            }
          }, 'i');
        };
      }
    });
    window.lucideReact = fallback;
  }
</script>
</head>
<body>
<div id="preview-root"></div>
<script>
  const __compiled = ${encodedCode};
  function wrapModule(mod) {
    if (mod && (typeof mod === 'object' || typeof mod === 'function')) {
      return Object.assign({ __esModule: true, default: mod }, mod);
    }
    return { __esModule: true, default: mod };
  }
  function reportError(payload) {
    if (window.parent && window.parent !== window) {
      const message = typeof payload === 'string' ? payload : (payload && (payload.stack || payload.message)) || 'Unknown error';
      window.parent.postMessage({ type: 'CODE_PLAYGROUND_ERROR', message }, '*');
    }
  }
  function createJsxRuntimeModule() {
    const runtime = window.ReactJSXRuntime || null;
    if (runtime && runtime.jsx && runtime.jsxs) {
      return wrapModule(runtime);
    }
    if (window.React && typeof window.React.createElement === 'function') {
      const shim = {
        Fragment: window.React.Fragment,
        jsx(type, props, key) {
          if (key !== undefined) props = Object.assign({}, props, { key });
          return window.React.createElement(type, props);
        },
        jsxs(type, props, key) {
          if (key !== undefined) props = Object.assign({}, props, { key });
          return window.React.createElement(type, props);
        },
        jsxDEV(type, props, key) {
          if (key !== undefined) props = Object.assign({}, props, { key });
          return window.React.createElement(type, props);
        }
      };
      return wrapModule(shim);
    }
    return wrapModule(null);
  }

  const requireMap = {
    react: (function () {
      const mod = window.React || {};
      return wrapModule(mod);
    })(),
    'react-dom': (function () {
      const mod = window.ReactDOM || {};
      return wrapModule(mod);
    })(),
    'react-dom/client': (function () {
      const mod = window.ReactDOMClient || window.ReactDOM || {};
      return wrapModule(mod);
    })(),
    'react/jsx-runtime': createJsxRuntimeModule(),
    'react/jsx-dev-runtime': createJsxRuntimeModule(),
    'lucide-react': (function () {
      const mod = window.lucideReact || {};
      return wrapModule(mod);
    })(),
  };

  function require(name) {
    if (!requireMap[name]) {
      throw new Error('未能解析依赖: ' + name);
    }
    return requireMap[name];
  }

  const module = { exports: {} };
  const exports = module.exports;

  try {
    const factory = new Function('exports', 'require', 'module', '__filename', '__dirname', __compiled);
    factory(exports, require, module, 'App.jsx', '/');
    const App = module.exports?.default || module.exports.App || module.exports;
    if (typeof App !== 'function') {
      throw new Error('请导出一个 React 组件，例如 export default function App() {...}');
    }
    const rootElement = document.getElementById('preview-root');
    const root = (window.ReactDOMClient && window.ReactDOMClient.createRoot)
      ? window.ReactDOMClient.createRoot(rootElement)
      : window.ReactDOM.render;
    if (root && root.render) {
      root.render(window.React.createElement(App));
    } else {
      window.ReactDOM.render(window.React.createElement(App), rootElement);
    }
  } catch (err) {
    reportError(err);
    const pre = document.createElement('pre');
    pre.textContent = err.stack || err.message;
    pre.style.padding = '24px';
    pre.style.margin = '0';
    pre.style.whiteSpace = 'pre-wrap';
    pre.style.lineHeight = '1.5';
    pre.style.color = '#fca5a5';
    pre.style.fontFamily = 'JetBrains Mono, monospace';
    document.body.innerHTML = '';
    document.body.appendChild(pre);
  }
  window.addEventListener('error', function (event) {
    reportError(event.error || event.message || '脚本错误');
  });
  window.addEventListener('unhandledrejection', function (event) {
    reportError(event.reason || event);
  });
</script>
</body>
</html>`;
  }

  function transpile(source) {
    if (!window.Babel) {
      throw new Error("Babel 尚未加载完成");
    }
    return window.Babel.transform(source, {
      sourceType: "module",
      presets: [
        ["react", { runtime: "classic" }],
      ],
      plugins: [
        "transform-modules-commonjs",
        "proposal-class-properties",
        "proposal-object-rest-spread",
        "proposal-optional-chaining",
        "proposal-nullish-coalescing-operator",
      ],
      filename: "App.jsx",
      retainLines: true,
    }).code;
  }

  let debounceTimer = null;
  let lastSource = "";
  let currentBlobUrl = null;

  function handleFrameLoad() {
    setCompileInfo("预览已更新", true);
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

  function updatePreview(immediate = false) {
    const source = normalizeSource(editor.value);
    if (source === lastSource && !immediate) {
      return;
    }
    hideError();

    if (!isBabelReady()) {
      waitForBabel(() => updatePreview(true));
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
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
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
        setStatus("已复制到剪贴板", "success");
        setTimeout(() => setStatus("实时预览"), 1600);
      }).catch(() => {
        setStatus("复制失败", "error");
      });
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
        setTimeout(() => setStatus("实时预览"), 1500);
      }
    }
  }

  function init() {
    const stored = localStorage.getItem(STORAGE_KEY);
    editor.value = stored || DEFAULT_SOURCE;
    editor.addEventListener("input", () => {
      localStorage.setItem(STORAGE_KEY, editor.value);
      scheduleUpdate();
    });
    buttons.forEach((btn) => btn.addEventListener("click", handleAction));

    const babelScript = document.querySelector('script[src*="babel.min.js"]');
    const triggerInitialRender = () => {
      if (pendingInitialRender) {
        return;
      }
      pendingInitialRender = true;
      if (babelScript) {
        babelScript.removeEventListener("load", triggerInitialRender);
      }
      if (document.readyState === "complete" || isBabelReady()) {
        scheduleUpdate(true);
      } else {
        waitForBabel(() => scheduleUpdate(true));
      }
    };

    if (isBabelReady()) {
      triggerInitialRender();
    } else if (babelScript) {
      babelScript.addEventListener("load", triggerInitialRender, { once: true });
      waitForBabel(triggerInitialRender);
    } else {
      waitForBabel(triggerInitialRender);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
