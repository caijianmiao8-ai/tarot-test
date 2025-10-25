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
  
  const TAILWIND_CDN_SOURCES = [
    'https://cdn.tailwindcss.com?plugins=forms,typography,aspect-ratio',
    'https://unpkg.com/@tailwindcss/browser@3.4.1?plugins=forms,typography,aspect-ratio',
    'https://cdn.jsdelivr.net/npm/@tailwindcss/browser@3.4.1?plugins=forms,typography,aspect-ratio',
  ];
  
  const TAILWIND_BASELINE_STYLESHEET = 'https://cdn.jsdelivr.net/npm/tailwindcss@3.4.1/dist/tailwind.min.css';
  const TAILWIND_BASELINE_STYLESHEET_FALLBACK = 'https://unpkg.com/tailwindcss@3.4.1/dist/tailwind.min.css';
  
  // ===== 🚀 增强版 Tailwind Fallback CSS =====
  // 包含更多常用的 Tailwind 类，特别是视觉效果相关的
  const TAILWIND_ENHANCED_FALLBACK_CSS = `:root { 
  color-scheme: dark; 
  --tw-bg-opacity: 1; 
  --tw-text-opacity: 1;
  --tw-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
  --tw-shadow-colored: 0 1px 3px 0 var(--tw-shadow-color), 0 1px 2px -1px var(--tw-shadow-color);
}

*, *::before, *::after { 
  box-sizing: border-box; 
  border-width: 0;
  border-style: solid;
  border-color: currentColor;
}

body { 
  margin: 0; 
  font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
  background: #020617; 
  color: rgba(226, 232, 240, 1); 
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

a { color: inherit; text-decoration: none; }
button { font-family: inherit; cursor: pointer; background: none; border: none; padding: 0; }
button:focus { outline: none; }

/* ===== 布局 ===== */
.font-sans { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important; }
.antialiased { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
.min-h-screen { min-height: 100vh !important; }
.flex { display: flex !important; }
.inline-flex { display: inline-flex !important; }
.grid { display: grid !important; }
.relative { position: relative !important; }
.absolute { position: absolute !important; }
.fixed { position: fixed !important; }
.pointer-events-none { pointer-events: none !important; }
.inset-0 { top: 0 !important; right: 0 !important; bottom: 0 !important; left: 0 !important; }
.z-10 { z-index: 10 !important; }
.z-50 { z-index: 50 !important; }

/* ===== Flexbox & Grid ===== */
.items-center { align-items: center !important; }
.items-start { align-items: flex-start !important; }
.justify-between { justify-content: space-between !important; }
.justify-center { justify-content: center !important; }
.justify-around { justify-content: space-around !important; }
.flex-col { flex-direction: column !important; }
.flex-1 { flex: 1 1 0% !important; }
.flex-shrink-0 { flex-shrink: 0 !important; }
.overflow-hidden { overflow: hidden !important; }
.overflow-y-auto { overflow-y: auto !important; }

.gap-1 { gap: 0.25rem !important; }
.gap-2 { gap: 0.5rem !important; }
.gap-3 { gap: 0.75rem !important; }
.gap-4 { gap: 1rem !important; }
.gap-6 { gap: 1.5rem !important; }
.gap-8 { gap: 2rem !important; }

.space-y-2 > :not([hidden]) ~ :not([hidden]) { margin-top: 0.5rem !important; }
.space-y-3 > :not([hidden]) ~ :not([hidden]) { margin-top: 0.75rem !important; }
.space-y-4 > :not([hidden]) ~ :not([hidden]) { margin-top: 1rem !important; }
.space-y-6 > :not([hidden]) ~ :not([hidden]) { margin-top: 1.5rem !important; }

.grid-cols-1 { grid-template-columns: repeat(1, minmax(0, 1fr)) !important; }
.grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
.grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; }

/* ===== 间距 ===== */
.p-2 { padding: 0.5rem !important; }
.p-3 { padding: 0.75rem !important; }
.p-4 { padding: 1rem !important; }
.p-6 { padding: 1.5rem !important; }
.p-8 { padding: 2rem !important; }
.px-2 { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
.px-3 { padding-left: 0.75rem !important; padding-right: 0.75rem !important; }
.px-4 { padding-left: 1rem !important; padding-right: 1rem !important; }
.px-5 { padding-left: 1.25rem !important; padding-right: 1.25rem !important; }
.px-6 { padding-left: 1.5rem !important; padding-right: 1.5rem !important; }
.px-8 { padding-left: 2rem !important; padding-right: 2rem !important; }
.py-1 { padding-top: 0.25rem !important; padding-bottom: 0.25rem !important; }
.py-2 { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; }
.py-3 { padding-top: 0.75rem !important; padding-bottom: 0.75rem !important; }
.py-4 { padding-top: 1rem !important; padding-bottom: 1rem !important; }
.pl-12 { padding-left: 3rem !important; }
.pr-4 { padding-right: 1rem !important; }
.pr-12 { padding-right: 3rem !important; }
.pt-3 { padding-top: 0.75rem !important; }
.pt-4 { padding-top: 1rem !important; }
.pb-3 { padding-bottom: 0.75rem !important; }

.m-0 { margin: 0 !important; }
.mb-1 { margin-bottom: 0.25rem !important; }
.mb-2 { margin-bottom: 0.5rem !important; }
.mb-3 { margin-bottom: 0.75rem !important; }
.mb-4 { margin-bottom: 1rem !important; }
.mb-6 { margin-bottom: 1.5rem !important; }
.mb-8 { margin-bottom: 2rem !important; }
.mt-1 { margin-top: 0.25rem !important; }
.mt-2 { margin-top: 0.5rem !important; }
.mt-3 { margin-top: 0.75rem !important; }
.mt-4 { margin-top: 1rem !important; }
.mt-6 { margin-top: 1.5rem !important; }
.mt-8 { margin-top: 2rem !important; }
.mt-auto { margin-top: auto !important; }
.mx-auto { margin-left: auto !important; margin-right: auto !important; }

/* ===== 尺寸 ===== */
.w-full { width: 100% !important; }
.w-1 { width: 0.25rem !important; }
.w-2 { width: 0.5rem !important; }
.w-12 { width: 3rem !important; }
.w-14 { width: 3.5rem !important; }
.w-16 { width: 4rem !important; }
.w-20 { width: 5rem !important; }
.w-24 { width: 6rem !important; }
.w-32 { width: 8rem !important; }
.w-64 { width: 16rem !important; }
.max-w-md { max-width: 28rem !important; }
.max-w-4xl { max-width: 56rem !important; }
.max-w-7xl { max-width: 80rem !important; }

.h-full { height: 100% !important; }
.h-1 { height: 0.25rem !important; }
.h-2 { height: 0.5rem !important; }
.h-12 { height: 3rem !important; }
.h-14 { height: 3.5rem !important; }
.h-16 { height: 4rem !important; }
.h-20 { height: 5rem !important; }
.h-24 { height: 6rem !important; }
.h-32 { height: 8rem !important; }

/* ===== 文字 ===== */
.text-xs { font-size: 0.75rem !important; line-height: 1rem !important; }
.text-sm { font-size: 0.875rem !important; line-height: 1.25rem !important; }
.text-base { font-size: 1rem !important; line-height: 1.5rem !important; }
.text-lg { font-size: 1.125rem !important; line-height: 1.75rem !important; }
.text-xl { font-size: 1.25rem !important; line-height: 1.75rem !important; }
.text-2xl { font-size: 1.5rem !important; line-height: 2rem !important; }
.text-3xl { font-size: 1.875rem !important; line-height: 2.25rem !important; }
.text-4xl { font-size: 2.25rem !important; line-height: 2.5rem !important; }
.text-5xl { font-size: 3rem !important; line-height: 1 !important; }

.font-medium { font-weight: 500 !important; }
.font-semibold { font-weight: 600 !important; }
.font-bold { font-weight: 700 !important; }
.font-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important; }

.text-left { text-align: left !important; }
.text-center { text-align: center !important; }
.uppercase { text-transform: uppercase !important; }
.truncate { overflow: hidden !important; text-overflow: ellipsis !important; white-space: nowrap !important; }
.tracking-wider { letter-spacing: 0.05em !important; }

/* ===== 颜色 ===== */
.text-white { color: rgb(255 255 255) !important; }
.text-slate-50 { color: rgb(248 250 252) !important; }
.text-slate-100 { color: rgb(241 245 249) !important; }
.text-slate-200 { color: rgb(226 232 240) !important; }
.text-slate-400 { color: rgb(148 163 184) !important; }
.text-slate-500 { color: rgb(100 116 139) !important; }
.text-slate-600 { color: rgb(71 85 105) !important; }
.text-slate-900 { color: rgb(15 23 42) !important; }
.text-gray-400 { color: rgb(156 163 175) !important; }
.text-gray-500 { color: rgb(107 114 128) !important; }
.text-gray-600 { color: rgb(75 85 99) !important; }
.text-red-500 { color: rgb(239 68 68) !important; }
.text-green-400 { color: rgb(74 222 128) !important; }
.text-green-500 { color: rgb(34 197 94) !important; }
.text-blue-500 { color: rgb(59 130 246) !important; }
.text-blue-600 { color: rgb(37 99 235) !important; }
.text-purple-500 { color: rgb(168 85 247) !important; }
.text-indigo-600 { color: rgb(79 70 229) !important; }
.text-yellow-400 { color: rgb(250 204 21) !important; }

.bg-white { background-color: rgb(255 255 255) !important; }
.bg-black { background-color: rgb(0 0 0) !important; }
.bg-slate-50 { background-color: rgb(248 250 252) !important; }
.bg-slate-800 { background-color: rgb(30 41 59) !important; }
.bg-slate-900 { background-color: rgb(15 23 42) !important; }
.bg-slate-950 { background-color: rgb(2 6 23) !important; }
.bg-gray-200 { background-color: rgb(229 231 235) !important; }
.bg-gray-400 { background-color: rgb(156 163 175) !important; }
.bg-blue-500 { background-color: rgb(59 130 246) !important; }
.bg-blue-600 { background-color: rgb(37 99 235) !important; }
.bg-green-500 { background-color: rgb(34 197 94) !important; }

/* ===== 🌟 背景渐变 (增强) ===== */
.bg-gradient-to-br { background-image: linear-gradient(to bottom right, var(--tw-gradient-stops)) !important; }
.bg-gradient-to-r { background-image: linear-gradient(to right, var(--tw-gradient-stops)) !important; }
.bg-gradient-to-t { background-image: linear-gradient(to top, var(--tw-gradient-stops)) !important; }
.bg-gradient-to-b { background-image: linear-gradient(to bottom, var(--tw-gradient-stops)) !important; }

.from-slate-900 { --tw-gradient-from: rgb(15 23 42); --tw-gradient-to: rgb(15 23 42 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-slate-950 { --tw-gradient-from: rgb(2 6 23); --tw-gradient-to: rgb(2 6 23 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-gray-50 { --tw-gradient-from: rgb(249 250 251); --tw-gradient-to: rgb(249 250 251 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-blue-400 { --tw-gradient-from: rgb(96 165 250); --tw-gradient-to: rgb(96 165 250 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-blue-500 { --tw-gradient-from: rgb(59 130 246); --tw-gradient-to: rgb(59 130 246 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-blue-600 { --tw-gradient-from: rgb(37 99 235); --tw-gradient-to: rgb(37 99 235 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-green-400 { --tw-gradient-from: rgb(74 222 128); --tw-gradient-to: rgb(74 222 128 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-purple-400 { --tw-gradient-from: rgb(192 132 252); --tw-gradient-to: rgb(192 132 252 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-purple-500 { --tw-gradient-from: rgb(168 85 247); --tw-gradient-to: rgb(168 85 247 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.from-transparent { --tw-gradient-from: transparent; --tw-gradient-to: transparent; --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }

.via-slate-950 { --tw-gradient-to: rgb(2 6 23 / 0); --tw-gradient-stops: var(--tw-gradient-from), rgb(2 6 23), var(--tw-gradient-to); }
.via-blue-50\/30 { --tw-gradient-to: rgb(239 246 255 / 0); --tw-gradient-stops: var(--tw-gradient-from), rgb(239 246 255 / 0.3), var(--tw-gradient-to); }
.via-white { --tw-gradient-to: rgb(255 255 255 / 0); --tw-gradient-stops: var(--tw-gradient-from), rgb(255 255 255), var(--tw-gradient-to); }
.via-white\/5 { --tw-gradient-to: rgb(255 255 255 / 0); --tw-gradient-stops: var(--tw-gradient-from), rgb(255 255 255 / 0.05), var(--tw-gradient-to); }
.via-transparent { --tw-gradient-to: transparent; --tw-gradient-stops: var(--tw-gradient-from), transparent, var(--tw-gradient-to); }

.to-black { --tw-gradient-to: rgb(0 0 0); }
.to-slate-950 { --tw-gradient-to: rgb(2 6 23); }
.to-gray-50 { --tw-gradient-to: rgb(249 250 251); }
.to-blue-500 { --tw-gradient-to: rgb(59 130 246); }
.to-blue-600 { --tw-gradient-to: rgb(37 99 235); }
.to-blue-700 { --tw-gradient-to: rgb(29 78 216); }
.to-green-600 { --tw-gradient-to: rgb(22 163 74); }
.to-purple-500 { --tw-gradient-to: rgb(168 85 247); }
.to-purple-600 { --tw-gradient-to: rgb(147 51 234); }
.to-transparent { --tw-gradient-to: transparent; }

/* ===== 边框 ===== */
.border { border-width: 1px !important; }
.border-t { border-top-width: 1px !important; }
.border-b { border-bottom-width: 1px !important; }
.border-l { border-left-width: 1px !important; }
.border-r { border-right-width: 1px !important; }
.border-l-4 { border-left-width: 4px !important; }

.border-white { border-color: rgb(255 255 255) !important; }
.border-slate-200 { border-color: rgb(226 232 240) !important; }
.border-slate-200\/10 { border-color: rgb(226 232 240 / 0.1) !important; }
.border-slate-200\/60 { border-color: rgb(226 232 240 / 0.6) !important; }
.border-slate-300 { border-color: rgb(203 213 225) !important; }
.border-slate-700 { border-color: rgb(51 65 85) !important; }
.border-slate-700\/50 { border-color: rgb(51 65 85 / 0.5) !important; }
.border-slate-800 { border-color: rgb(30 41 59) !important; }
.border-slate-800\/50 { border-color: rgb(30 41 59 / 0.5) !important; }
.border-gray-200\/10 { border-color: rgb(229 231 235 / 0.1) !important; }
.border-gray-400\/20 { border-color: rgb(156 163 175 / 0.2) !important; }
.border-blue-500 { border-color: rgb(59 130 246) !important; }
.border-blue-500\/20 { border-color: rgb(59 130 246 / 0.2) !important; }
.border-green-500\/20 { border-color: rgb(34 197 94 / 0.2) !important; }
.border-transparent { border-color: transparent !important; }

.rounded-xl { border-radius: 0.75rem !important; }
.rounded-2xl { border-radius: 1rem !important; }
.rounded-3xl { border-radius: 1.5rem !important; }
.rounded-full { border-radius: 9999px !important; }
.rounded-t-3xl { border-top-left-radius: 1.5rem !important; border-top-right-radius: 1.5rem !important; }

/* ===== 🎨 阴影效果 (增强) ===== */
.shadow-sm { box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05) !important; }
.shadow { box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1) !important; }
.shadow-md { box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1) !important; }
.shadow-lg { box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1) !important; }
.shadow-xl { box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1) !important; }
.shadow-2xl { box-shadow: 0 25px 50px -12px rgb(0 0 0 / 0.25) !important; }
.shadow-inner { box-shadow: inset 0 2px 4px 0 rgb(0 0 0 / 0.05) !important; }

/* 彩色阴影 */
.shadow-blue-500\/10 { box-shadow: 0 20px 25px -5px rgb(59 130 246 / 0.1), 0 8px 10px -6px rgb(59 130 246 / 0.1) !important; }
.shadow-blue-500\/20 { box-shadow: 0 20px 25px -5px rgb(59 130 246 / 0.2), 0 8px 10px -6px rgb(59 130 246 / 0.2) !important; }
.shadow-blue-500\/30 { box-shadow: 0 20px 25px -5px rgb(59 130 246 / 0.3), 0 8px 10px -6px rgb(59 130 246 / 0.3) !important; }
.shadow-blue-500\/40 { box-shadow: 0 20px 25px -5px rgb(59 130 246 / 0.4), 0 8px 10px -6px rgb(59 130 246 / 0.4) !important; }
.shadow-green-500\/30 { box-shadow: 0 20px 25px -5px rgb(34 197 94 / 0.3), 0 8px 10px -6px rgb(34 197 94 / 0.3) !important; }
.shadow-purple-500\/30 { box-shadow: 0 20px 25px -5px rgb(168 85 247 / 0.3), 0 8px 10px -6px rgb(168 85 247 / 0.3) !important; }

/* ===== 💫 毛玻璃效果 (backdrop-blur) ===== */
.backdrop-blur-sm { backdrop-filter: blur(4px) !important; }
.backdrop-blur { backdrop-filter: blur(8px) !important; }
.backdrop-blur-md { backdrop-filter: blur(12px) !important; }
.backdrop-blur-lg { backdrop-filter: blur(16px) !important; }
.backdrop-blur-xl { backdrop-filter: blur(24px) !important; }
.backdrop-blur-2xl { backdrop-filter: blur(40px) !important; }

/* ===== 透明度 ===== */
.bg-white\/80 { background-color: rgb(255 255 255 / 0.8) !important; }
.bg-white\/90 { background-color: rgb(255 255 255 / 0.9) !important; }
.bg-black\/50 { background-color: rgb(0 0 0 / 0.5) !important; }
.bg-slate-900\/80 { background-color: rgb(15 23 42 / 0.8) !important; }
.bg-slate-900\/90 { background-color: rgb(15 23 42 / 0.9) !important; }
.bg-blue-500\/10 { background-color: rgb(59 130 246 / 0.1) !important; }
.bg-blue-500\/20 { background-color: rgb(59 130 246 / 0.2) !important; }
.bg-green-500\/10 { background-color: rgb(34 197 94 / 0.1) !important; }
.bg-green-500\/15 { background-color: rgb(34 197 94 / 0.15) !important; }
.bg-purple-500\/10 { background-color: rgb(168 85 247 / 0.1) !important; }

/* ===== ✨ 过渡动画 (transition) ===== */
.transition { transition-property: color, background-color, border-color, text-decoration-color, fill, stroke, opacity, box-shadow, transform, filter, backdrop-filter !important; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1) !important; transition-duration: 150ms !important; }
.transition-all { transition-property: all !important; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1) !important; transition-duration: 150ms !important; }
.transition-colors { transition-property: color, background-color, border-color, text-decoration-color, fill, stroke !important; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1) !important; transition-duration: 150ms !important; }
.transition-transform { transition-property: transform !important; transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1) !important; transition-duration: 150ms !important; }

.duration-150 { transition-duration: 150ms !important; }
.duration-200 { transition-duration: 200ms !important; }
.duration-300 { transition-duration: 300ms !important; }
.duration-500 { transition-duration: 500ms !important; }

/* ===== 🎯 Transform ===== */
.transform { transform: translate(var(--tw-translate-x), var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y)) !important; }
.scale-95 { --tw-scale-x: 0.95; --tw-scale-y: 0.95; transform: scale(0.95) !important; }
.scale-105 { --tw-scale-x: 1.05; --tw-scale-y: 1.05; transform: scale(1.05) !important; }
.scale-110 { --tw-scale-x: 1.1; --tw-scale-y: 1.1; transform: scale(1.1) !important; }
.-translate-x-1\/2 { --tw-translate-x: -50%; transform: translateX(-50%) !important; }
.-translate-y-1\/2 { --tw-translate-y: -50%; transform: translateY(-50%) !important; }
.translate-y-0 { --tw-translate-y: 0px; transform: translateY(0) !important; }
.-translate-y-2 { --tw-translate-y: -0.5rem; transform: translateY(-0.5rem) !important; }
.rotate-12 { --tw-rotate: 12deg; transform: rotate(12deg) !important; }

/* ===== 🎬 动画 ===== */
.animate-pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite !important; }
.animate-bounce { animation: bounce 1s infinite !important; }
.animate-spin { animation: spin 1s linear infinite !important; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes bounce {
  0%, 100% { transform: translateY(-25%); animation-timing-function: cubic-bezier(0.8, 0, 1, 1); }
  50% { transform: translateY(0); animation-timing-function: cubic-bezier(0, 0, 0.2, 1); }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ===== Hover状态 ===== */
.hover\\:bg-slate-50:hover { background-color: rgb(248 250 252) !important; }
.hover\\:bg-slate-800:hover { background-color: rgb(30 41 59) !important; }
.hover\\:bg-slate-800\\/60:hover { background-color: rgb(30 41 59 / 0.6) !important; }
.hover\\:bg-blue-600:hover { background-color: rgb(37 99 235) !important; }
.hover\\:bg-blue-700:hover { background-color: rgb(29 78 216) !important; }
.hover\\:text-blue-500:hover { color: rgb(59 130 246) !important; }
.hover\\:shadow-lg:hover { box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1) !important; }
.hover\\:shadow-xl:hover { box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1) !important; }
.hover\\:shadow-2xl:hover { box-shadow: 0 25px 50px -12px rgb(0 0 0 / 0.25) !important; }
.hover\\:shadow-blue-500\\/30:hover { box-shadow: 0 20px 25px -5px rgb(59 130 246 / 0.3), 0 8px 10px -6px rgb(59 130 246 / 0.3) !important; }
.hover\\:scale-105:hover { transform: scale(1.05) !important; }
.hover\\:scale-110:hover { transform: scale(1.1) !important; }
.hover\\:-translate-y-2:hover { transform: translateY(-0.5rem) !important; }

/* ===== Active状态 ===== */
.active\\:scale-95:active { transform: scale(0.95) !important; }

/* ===== Focus状态 ===== */
.focus\\:outline-none:focus { outline: 2px solid transparent !important; outline-offset: 2px !important; }
.focus\\:ring-2:focus { box-shadow: 0 0 0 3px var(--tw-ring-color) !important; }
.focus\\:ring-blue-500:focus { --tw-ring-color: rgb(59 130 246 / 0.5); }
.focus\\:border-transparent:focus { border-color: transparent !important; }
.focus\\:border-blue-500:focus { border-color: rgb(59 130 246) !important; }

/* ===== 响应式 ===== */
@media (min-width: 768px) {
  .md\\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; }
}

@media (min-width: 1024px) {
  .lg\\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
  .lg\\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; }
  .lg\\:grid-cols-\\[320px_1fr\\] { grid-template-columns: 320px 1fr !important; }
}

/* ===== 暗色模式支持 ===== */
.dark\\:bg-zinc-900:is(.dark *) { background-color: rgb(24 24 27) !important; }
.dark\\:text-white:is(.dark *) { color: rgb(255 255 255) !important; }
.dark\\:from-white\\/5:is(.dark *) { --tw-gradient-from: rgb(255 255 255 / 0.05); --tw-gradient-to: rgb(255 255 255 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }
.dark\\:from-white\\/10:is(.dark *) { --tw-gradient-from: rgb(255 255 255 / 0.1); --tw-gradient-to: rgb(255 255 255 / 0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to); }

/* ===== 其他实用类 ===== */
.cursor-pointer { cursor: pointer !important; }
.select-none { user-select: none !important; }
.appearance-none { appearance: none !important; }
.outline-none { outline: 2px solid transparent !important; outline-offset: 2px !important; }
`;

  function setStatus(text = "实时预览", state = "idle") {
    if (!statusLabel) return;
    statusLabel.textContent = text;
    statusLabel.classList.remove("is-idle", "is-running", "is-error", "is-success");
    statusLabel.classList.add("is-" + state);
  }

  function setCompileInfo(text, loading = false) {
    if (!compileBadge) return;
    compileBadge.textContent = text;
    if (loading) {
      compileBadge.classList.add("is-compiling");
    } else {
      compileBadge.classList.remove("is-compiling");
    }
  }

  function showError(message, title = "编译错误") {
    if (overlay) {
      const pre = overlay.querySelector("pre") || document.createElement("pre");
      pre.textContent = message;
      pre.style.cssText = "color:#fca5a5;font-family:monospace;white-space:pre-wrap;line-height:1.6";
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
    if (overlay) {
      overlay.style.display = "none";
    }
  }

  function normalizeSource(src) {
    return (src || "").trim();
  }

  async function loadScript(url, timeout = 8000) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const timer = setTimeout(() => {
        script.remove();
        reject(new Error(`加载超时: ${url}`));
      }, timeout);
      script.onload = () => {
        clearTimeout(timer);
        resolve();
      };
      script.onerror = () => {
        clearTimeout(timer);
        script.remove();
        reject(new Error(`加载失败: ${url}`));
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
          console.log(`✅ Babel 加载成功: ${src}`);
          return;
        }
      } catch (err) {
        console.warn(`⚠️ Babel 加载失败: ${src}`, err);
      }
    }
    throw new Error("所有 Babel CDN 源均加载失败");
  }

  function ensureBabelLoaded() {
    if (window.Babel) {
      return Promise.resolve();
    }
    if (babelLoadingPromise) {
      return babelLoadingPromise;
    }
    babelLoadingPromise = tryLoadBabel();
    return babelLoadingPromise;
  }

  function buildPreviewHtml(compiledCode) {
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>Preview</title>
  
  <!-- 🚀 Tailwind CSS Play CDN - 支持所有特性！ -->
  <script src="https://cdn.tailwindcss.com"></script>
  
  <!-- Tailwind 配置 -->
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          animation: {
            'pulse': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
            'bounce': 'bounce 1s infinite',
            'spin': 'spin 1s linear infinite',
          }
        }
      }
    }
  </script>
  
  <!-- Fallback CSS - 如果 CDN 失败 -->
  <style>
    ${TAILWIND_ENHANCED_FALLBACK_CSS}
  </style>
  
  <!-- React 和其他依赖 -->
  ${Object.entries(CDN_POLYFILLS).map(
    ([, url]) => `<script src="${url}" crossorigin="anonymous"></script>`
  ).join("\n  ")}
  
  <style>
    /* 确保基础样式 */
    * { box-sizing: border-box; }
    body { margin: 0; padding: 0; }
    #root { width: 100%; min-height: 100vh; }
  </style>
</head>
<body>
<div id="root"></div>
<script>
  function reportError(err) {
    if (window.parent && window.parent.postMessage) {
      window.parent.postMessage({
        type: 'CODE_PLAYGROUND_ERROR',
        message: err && err.message ? err.message : String(err)
      }, '*');
    }
  }
  
  // 等待所有依赖加载完成
  function waitForDependencies() {
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        // 检查所有必需的依赖
        const hasReact = window.React;
        const hasReactDOM = window.ReactDOM;
        const hasLucide = window.lucideReact || window.LucideReact || window['lucide-react'];
        
        if (hasReact && hasReactDOM && hasLucide) {
          clearInterval(checkInterval);
          console.log('✅ 所有依赖加载完成', {
            React: !!hasReact,
            ReactDOM: !!hasReactDOM,
            LucideReact: !!hasLucide
          });
          resolve();
        }
      }, 50);
      
      // 超时保护
      setTimeout(() => {
        clearInterval(checkInterval);
        const hasReact = window.React;
        const hasReactDOM = window.ReactDOM;
        const hasLucide = window.lucideReact || window.LucideReact || window['lucide-react'];
        
        if (!hasReact || !hasReactDOM) {
          reportError(new Error('React 加载超时'));
        } else if (!hasLucide) {
          console.warn('⚠️ Lucide React 图标库加载超时，图标可能无法显示');
        }
        resolve();
      }, 8000);
    });
  }
  
  waitForDependencies().then(() => {
    try {
      // ===== 🎯 创建模块解析系统 =====
      const exports = {};
      const module = { exports: exports };
      
      // 创建 require 函数来解析模块
      const require = function(moduleName) {
        // React 模块
        if (moduleName === 'react') {
          return window.React;
        }
        
        // ReactDOM 模块
        if (moduleName === 'react-dom') {
          return window.ReactDOM;
        }
        
        // Lucide React 图标库
        if (moduleName === 'lucide-react') {
          // lucide-react UMD 会暴露为 window.lucideReact 或 window.LucideReact
          return window.lucideReact || window.LucideReact || window['lucide-react'] || {};
        }
        
        // 如果模块未找到，返回空对象
        console.warn('Module not found:', moduleName);
        return {};
      };
      
      // 执行编译后的代码
      ${compiledCode}
      
      const App = exports.default || module.exports.default || module.exports || exports;
      
      if (!App || typeof App !== 'function') {
        throw new Error('无效的组件导出：请确保使用 export default');
      }
      
      const root = document.getElementById('root');
      
      // 兼容 React 18 和旧版本
      if (window.ReactDOM.createRoot) {
        const reactRoot = window.ReactDOM.createRoot(root);
        reactRoot.render(window.React.createElement(App));
      } else {
        window.ReactDOM.render(window.React.createElement(App), root);
      }
      
      // 通知父窗口渲染成功
      if (window.parent && window.parent.postMessage) {
        window.parent.postMessage({type:'CODE_PLAYGROUND_SUCCESS'},'*');
      }
      
    } catch (err) {
      reportError(err);
      document.body.innerHTML = '<div style="padding:32px;font-family:monospace;background:#1a1a1a;color:#fff;min-height:100vh"><h2 style="color:#ef4444;margin-bottom:16px">❌ 渲染错误</h2><pre style="background:#0a0a0a;padding:20px;border-radius:8px;border-left:4px solid #ef4444;overflow-x:auto;line-height:1.6">' + (err.stack || err.message) + '</pre></div>';
    }
  });
  
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
    setCompileInfo("预览已更新 ✨", true);
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

  function handleBabelFailure(error) {
    const message = (error && error.message) || "无法加载 Babel 编译器，暂时无法编译预览。";
    const guidance = `${message}\n请检查网络连接或点击"重试编译器"按钮后再试。`;
    showError(guidance, "加载失败");
    setStatus("编译器加载失败", "error");
    if (compilerRetryButton) {
      compilerRetryButton.classList.add("is-visible");
    }
  }

  async function updatePreview(immediate = false) {
    const source = normalizeSource(editor.value);
    if (source === lastSource && !immediate) {
      return;
    }
    hideError();

    try {
      await ensureBabelLoaded();
    } catch (err) {
      console.error(err);
      handleBabelFailure(err);
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
    debounceTimer = setTimeout(() => {
      updatePreview(false);
    }, 320);
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
    if (action === "reload-compiler") {
      setCompileInfo("重新加载中…", true);
      setStatus("重新加载编译器", "running");
      ensureBabelLoaded()
        .then(() => {
          scheduleUpdate(true);
        })
        .catch((error) => {
          console.error(error);
          handleBabelFailure(error);
        });
    }
  }

  function init() {
    console.log("🚀 Playground Enhanced - 已加载增强版 Tailwind 支持！");
    const stored = localStorage.getItem(STORAGE_KEY);
    editor.value = stored || DEFAULT_SOURCE;
    editor.addEventListener("input", () => {
      localStorage.setItem(STORAGE_KEY, editor.value);
      scheduleUpdate();
    });
    buttons.forEach((btn) => btn.addEventListener("click", handleAction));

    ensureBabelLoaded()
      .then(() => {
        scheduleUpdate(true);
      })
      .catch((error) => {
        console.error(error);
        handleBabelFailure(error);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();