(function () {
  const editor = document.getElementById("code-editor");
  const frame = document.getElementById("preview-frame");
  const overlay = document.getElementById("error-overlay");
  const compileBadge = document.getElementById("compile-info");
  const statusLabel = document.getElementById("status-label");
  const buttons = document.querySelectorAll("[data-action]");
  const compilerRetryButton = document.querySelector('[data-action="reload-compiler"]');

  const STORAGE_KEY = "code-playground-source";

  // 多 CDN 兜底加载 Babel
  const BABEL_SOURCES = [
    "https://unpkg.com/@babel/standalone@7.23.9/babel.min.js",
    "https://cdn.jsdelivr.net/npm/@babel/standalone@7.23.9/babel.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.9/babel.min.js",
  ];
  const BABEL_ATTEMPT_TIMEOUT = 8000;
  let babelLoadingPromise = null;

  // React / ReactDOM / lucide-react 来自 CDN
  const CDN_POLYFILLS = {
    react: `https://unpkg.com/react@18/umd/react.development.js`,
    "react-dom": `https://unpkg.com/react-dom@18/umd/react-dom.development.js`,
    "lucide-react": `https://unpkg.com/lucide-react@0.379.0/dist/lucide-react.umd.js`,
  };

  // -------------------------------------------------
  // 加强版“离线 Tailwind 子集”
  // 现在覆盖：
  // - iPhone 外壳的定制尺寸 / 圆角
  // - 更细颗粒的 gap / spacing
  // - 边框、阴影、毛玻璃、渐变、暗色面板
  // - 布局 (flex-shrink-0 / min-w-0 / max-w-6xl...)
  // -------------------------------------------------
  const CORE_CSS = `
:root {
  color-scheme: dark;
  --tw-bg-opacity:1;
  --tw-text-opacity:1;
  --tw-from: rgba(15,23,42,1);
  --tw-via: rgba(15,23,42,0.85);
  --tw-to: rgba(2,6,23,1);
}
*,
*::before,
*::after {
  box-sizing: border-box;
}
body {
  margin:0;
  font-family:'Inter',system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#020617;
  color:rgba(226,232,240,1);
  line-height:1.5;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
a {
  color: inherit;
  text-decoration:none;
}
button {
  font-family: inherit;
  cursor:pointer;
  background:none;
  border:0;
  color:inherit;
}
button:focus {
  outline: none;
}
img,svg {
  display:block;
  max-width:100%;
}
#preview-root {
  width:100vw;
  height:100vh;
  overflow:hidden;
}

/* 滚动条 - 类 iOS/macOS 的细滚动条 */
::-webkit-scrollbar {
  width:10px;
  height:10px;
}
::-webkit-scrollbar-thumb {
  background:rgba(148,163,184,0.2);
  border-radius:999px;
}

/* ===== 布局 / Flex / Grid / 位置 / 尺寸控制 ===== */
.flex { display:flex !important; }
.inline-flex { display:inline-flex !important; }
.flex-col { flex-direction:column !important; }

.flex-1 { flex:1 1 0% !important; }
.flex-shrink-0 { flex-shrink:0 !important; }
.min-w-0 { min-width:0 !important; }

.items-center { align-items:center !important; }
.items-start { align-items:flex-start !important; }
.justify-between { justify-content:space-between !important; }
.justify-around { justify-content:space-around !important; }
.justify-center { justify-content:center !important; }

.grid { display:grid !important; }
.grid-cols-3 { grid-template-columns:repeat(3,minmax(0,1fr)) !important; }
.grid-cols-4 { grid-template-columns:repeat(4,minmax(0,1fr)) !important; }
@media (min-width:768px){
  .md\\:grid-cols-3 { grid-template-columns:repeat(3,minmax(0,1fr)) !important; }
}
@media (min-width:1024px){
  .lg\\:grid-cols-\\[320px_1fr\\] { grid-template-columns:320px 1fr !important; }
  .grid-cols-4 { grid-template-columns:repeat(4,minmax(0,1fr)) !important; }
}

/* 尺寸 / 盒子约束 */
.min-h-screen { min-height:100vh !important; }
.h-screen { height:100vh !important; }
.h-full { height:100% !important; }
.w-full { width:100% !important; }

.max-w-md { max-width:28rem !important; }
.max-w-4xl { max-width:56rem !important; }
.max-w-6xl { max-width:72rem !important; }

.h-\\[280px\\] { height:280px !important; }
.h-\\[360px\\] { height:360px !important; }
.w-64 { width:16rem !important; }

/* iPhone 15 Pro Max-ish 宽高（你的 PhoneFrame 用的） */
.w-\\[393px\\] { width:393px !important; }
.h-\\[852px\\] { height:852px !important; }

.w-12 { width:3rem !important; }
.h-12 { height:3rem !important; }
.w-14 { width:3.5rem !important; }
.h-14 { height:3.5rem !important; }
.w-16 { width:4rem !important; }
.h-16 { height:4rem !important; }
.w-20 { width:5rem !important; }
.h-20 { height:5rem !important; }
.w-24 { width:6rem !important; }
.h-24 { height:6rem !important; }
.h-7 { height:1.75rem !important; }

.w-8 { width:2rem !important; }
.h-8 { height:2rem !important; }
.w-10 { width:2.5rem !important; }
.h-10 { height:2.5rem !important; }

.w-1 { width:0.25rem !important; }
.h-1 { height:0.25rem !important; }
.w-1\\.5 { width:0.375rem !important; }
.h-1\\.5 { height:0.375rem !important; }
.w-2 { width:0.5rem !important; }
.h-2 { height:0.5rem !important; }
.w-2\\.5 { width:0.625rem !important; }
.h-2\\.5 { height:0.625rem !important; }
.w-3 { width:0.75rem !important; }
.h-3 { height:0.75rem !important; }
.w-5 { width:1.25rem !important; }
.h-5 { height:1.25rem !important; }
.w-px { width:1px !important; }

.left-0 { left:0 !important; }
.right-0 { right:0 !important; }
.top-0 { top:0 !important; }
.bottom-0 { bottom:0 !important; }
.left-6 { left:1.5rem !important; }
.right-6 { right:1.5rem !important; }
.left-1\\/2 { left:50% !important; }
.top-1\\/2 { top:50% !important; }
.top-12 { top:3rem !important; }
.top-32 { top:8rem !important; }
.top-40 { top:10rem !important; }
.top-48 { top:12rem !important; }
.bottom-6 { bottom:1.5rem !important; }

.top-1\\/4 { top:25% !important; }
.h-1\\/3 { height:33.333333% !important; }

.inset-0 { top:0 !important; right:0 !important; bottom:0 !important; left:0 !important; }

.fixed { position:fixed !important; }
.absolute { position:absolute !important; }
.relative { position:relative !important; }
.z-10 { z-index:10 !important; }
.z-20 { z-index:20 !important; }
.z-30 { z-index:30 !important; }
.z-40 { z-index:40 !important; }
.z-50 { z-index:50 !important; }

/* iOS 底部安全区 */
.pb-\\[env\\(safe-area-inset-bottom\\)\\] {
  padding-bottom: env(safe-area-inset-bottom, 0px) !important;
}
.bottom-\\[calc\\(5rem\\+env\\(safe-area-inset-bottom\\)\\)\\] {
  bottom: calc(5rem + env(safe-area-inset-bottom,0px)) !important;
}

/* transform 变量式组合，支持 translate + rotate 同时存在 */
.transform {
  --tw-translate-x: 0;
  --tw-translate-y: 0;
  --tw-rotate: 0;
  transform: translate(var(--tw-translate-x), var(--tw-translate-y)) rotate(var(--tw-rotate));
}
.-translate-x-1\\/2 { --tw-translate-x:-50%; }
.-translate-y-1\\/2 { --tw-translate-y:-50%; }
.rotate-180 { --tw-rotate:180deg; }

/* overflow / scroll */
.overflow-hidden { overflow:hidden !important; }
.overflow-y-auto { overflow-y:auto !important; }
.overscroll-contain { overscroll-behavior:contain !important; }

/* pointer-events */
.pointer-events-none { pointer-events:none !important; }

/* ===== gap / spacing / padding / margin / radius / shadow / border ===== */
.gap-1 { gap:0.25rem !important; }
.gap-1\\.5 { gap:0.375rem !important; }
.gap-2 { gap:0.5rem !important; }
.gap-3 { gap:0.75rem !important; }
.gap-4 { gap:1rem !important; }
.gap-6 { gap:1.5rem !important; }

.space-y-2 > :not([hidden]) ~ :not([hidden]) { margin-top:0.5rem !important; }
.space-y-3 > :not([hidden]) ~ :not([hidden]) { margin-top:0.75rem !important; }
.space-y-4 > :not([hidden]) ~ :not([hidden]) { margin-top:1rem !important; }
.space-y-6 > :not([hidden]) ~ :not([hidden]) { margin-top:1.5rem !important; }

.p-2 { padding:0.5rem !important; }
.p-3 { padding:0.75rem !important; }
.p-4 { padding:1rem !important; }
.p-6 { padding:1.5rem !important; }
.p-8 { padding:2rem !important; }

.px-2 { padding-left:0.5rem !important; padding-right:0.5rem !important; }
.px-3 { padding-left:0.75rem !important; padding-right:0.75rem !important; }
.px-4 { padding-left:1rem !important; padding-right:1rem !important; }
.px-6 { padding-left:1.5rem !important; padding-right:1.5rem !important; }
.px-8 { padding-left:2rem !important; padding-right:2rem !important; }
.px-10 { padding-left:2.5rem !important; padding-right:2.5rem !important; }

.py-0\\.5 { padding-top:0.125rem !important; padding-bottom:0.125rem !important; }
.py-1 { padding-top:0.25rem !important; padding-bottom:0.25rem !important; }
.py-1\\.5 { padding-top:0.375rem !important; padding-bottom:0.375rem !important; }
.py-2 { padding-top:0.5rem !important; padding-bottom:0.5rem !important; }
.py-3 { padding-top:0.75rem !important; padding-bottom:0.75rem !important; }
.py-4 { padding-top:1rem !important; padding-bottom:1rem !important; }
.py-8 { padding-top:2rem !important; padding-bottom:2rem !important; }

.pb-10 { padding-bottom:2.5rem !important; }

.mt-1 { margin-top:0.25rem !important; }
.mt-2 { margin-top:0.5rem !important; }
.mt-3 { margin-top:0.75rem !important; }
.mt-4 { margin-top:1rem !important; }
.mt-6 { margin-top:1.5rem !important; }
.mt-8 { margin-top:2rem !important; }

.mb-2 { margin-bottom:0.5rem !important; }
.mb-3 { margin-bottom:0.75rem !important; }
.mb-4 { margin-bottom:1rem !important; }
.mb-6 { margin-bottom:1.5rem !important; }
.mb-8 { margin-bottom:2rem !important; }

.mx-auto { margin-left:auto !important; margin-right:auto !important; }

/* 圆角，包括你定制的手机壳大圆角 */
.rounded-full { border-radius:9999px !important; }
.rounded-xl { border-radius:0.75rem !important; }
.rounded-lg { border-radius:0.5rem !important; }
.rounded-2xl { border-radius:1rem !important; }
.rounded-3xl { border-radius:1.5rem !important; }
.rounded-l { border-top-left-radius:0.25rem !important; border-bottom-left-radius:0.25rem !important; }
.rounded-r { border-top-right-radius:0.25rem !important; border-bottom-right-radius:0.25rem !important; }
.rounded-b-3xl { border-bottom-left-radius:1.5rem !important; border-bottom-right-radius:1.5rem !important; }
.rounded-\\[3rem\\] { border-radius:3rem !important; }
.rounded-\\[2\\.5rem\\] { border-radius:2.5rem !important; }

/* 阴影，接近卡片/浮层的 Apple 式投影 */
.shadow-sm { box-shadow:0 10px 20px rgba(0,0,0,0.4) !important; }
.shadow-md { box-shadow:0 20px 40px rgba(0,0,0,0.45) !important; }
.shadow-lg { box-shadow:0 30px 60px rgba(0,0,0,0.5) !important; }
.shadow-xl { box-shadow:0 25px 50px -12px rgba(15,23,42,0.45) !important; }
.shadow-2xl { box-shadow:0 35px 70px -20px rgba(14,21,38,0.55) !important; }

/* 边框线（卡片分隔线、手机外壳缝隙） */
.border { border-width:1px !important; border-style:solid !important; border-color:rgba(148,163,184,0.18) !important; }
.border-t { border-top-width:1px !important; border-top-style:solid !important; }
.border-b { border-bottom-width:1px !important; border-bottom-style:solid !important; }
.border-r { border-right-width:1px !important; border-right-style:solid !important; }
.border-l { border-left-width:1px !important; border-left-style:solid !important; }

.border-transparent { border-color:transparent !important; }

.border-slate-700\\/60 { border-color:rgba(51,65,85,0.6) !important; }
.border-slate-800\\/60 { border-color:rgba(30,41,59,0.6) !important; }
.border-slate-800\\/70 { border-color:rgba(30,41,59,0.7) !important; }
.border-slate-900\\/30 { border-color:rgba(15,23,42,0.3) !important; }
.border-slate-900\\/60 { border-color:rgba(15,23,42,0.6) !important; }

.border-gray-200 { border-color:rgba(229,231,235,1) !important; }
.border-gray-300 { border-color:rgba(209,213,219,1) !important; }
.border-zinc-700 { border-color:rgba(63,63,70,1) !important; }
.border-zinc-800 { border-color:rgba(39,39,42,1) !important; }
.border-zinc-900 { border-color:rgba(24,24,27,1) !important; }
.border-white\\/20 { border-color:rgba(255,255,255,0.2) !important; }
.border-red-500\\/20 { border-color:rgba(239,68,68,0.2) !important; }

/* ===== 背景色 / 渐变 / 毛玻璃 / 透明块 ===== */

/* Tailwind 风格渐变：bg-gradient-to-br + from/via/to 变量 */
.bg-gradient-to-br {
  background-image: linear-gradient(
    135deg,
    var(--tw-from, rgba(15,23,42,1)),
    var(--tw-via, rgba(15,23,42,0.85)),
    var(--tw-to, rgba(2,6,23,1))
  ) !important;
}

/* 默认深色渐变 */
.from-slate-900 { --tw-from: rgba(15,23,42,1) !important; }
.via-slate-950 { --tw-via: rgba(2,6,23,0.75) !important; }
.to-black { --tw-to: rgba(0,0,0,1) !important; }

/* 桌面蓝紫背景 */
.from-blue-600 { --tw-from: rgba(37,99,235,1) !important; }
.via-blue-700 { --tw-via: rgba(29,78,216,1) !important; }
.to-blue-900 { --tw-to: rgba(30,58,138,1) !important; }

/* 卡片内 overlay: 天蓝→透明→紫 */
.from-sky-500\\/10 { --tw-from: rgba(14,165,233,0.1) !important; }
.via-transparent { --tw-via: transparent !important; }
.to-purple-500\\/10 { --tw-to: rgba(168,85,247,0.1) !important; }

/* 常规背景块 */
.bg-black\\/60 { background-color:rgba(0,0,0,0.6) !important; color:#fff !important; }
.bg-black\\/70 { background-color:rgba(0,0,0,0.7) !important; color:#fff !important; }
.bg-black\\/90 { background-color:rgba(0,0,0,0.9) !important; color:#fff !important; }

.bg-white { background-color:#ffffff !important; color:#0f172a !important; }
.bg-white\\/20 { background-color:rgba(255,255,255,0.2) !important; }
.bg-white\\/30 { background-color:rgba(255,255,255,0.3) !important; }
.bg-white\\/95 { background-color:rgba(255,255,255,0.95) !important; color:#0f172a !important; }

.bg-gray-50 { background-color:rgba(249,250,251,1) !important; color:#0f172a !important; }
.bg-gray-100 { background-color:rgba(243,244,246,1) !important; color:#0f172a !important; }
.bg-gray-400 { background-color:rgba(156,163,175,1) !important; color:#fff !important; }
.bg-gray-400\\/10 { background-color:rgba(156,163,175,0.1) !important; color:rgba(156,163,175,1) !important; }
.bg-gray-600 { background-color:rgba(75,85,99,1) !important; color:#fff !important; }
.bg-gray-800 { background-color:rgba(31,41,55,1) !important; }

.bg-zinc-900 { background-color:rgba(24,24,27,1) !important; color:#fff !important; }
.bg-zinc-900\\/50 { background-color:rgba(24,24,27,0.5) !important; color:#fff !important; }
.bg-zinc-900\\/80 { background-color:rgba(24,24,27,0.8) !important; color:#fff !important; }

.bg-slate-900\\/80 { background-color:rgba(15,23,42,0.8) !important; }
.bg-slate-900\\/70 { background-color:rgba(15,23,42,0.7) !important; }
.bg-slate-900\\/60 { background-color:rgba(15,23,42,0.6) !important; }
.bg-slate-900\\/30 { background-color:rgba(15,23,42,0.3) !important; }
.bg-slate-900\\/20 { background-color:rgba(15,23,42,0.2) !important; }
.bg-slate-900\\/10 { background-color:rgba(15,23,42,0.1) !important; }
.bg-slate-900\\/5  { background-color:rgba(15,23,42,0.05) !important; }
.bg-slate-950\\/60 { background-color:rgba(2,6,23,0.6) !important; }
.bg-slate-950\\/80 { background-color:rgba(2,6,23,0.8) !important; }

.bg-sky-400\\/10 { background-color:rgba(56,189,248,0.1) !important; color:rgba(56,189,248,1) !important; }
.bg-sky-500\\/10 { background-color:rgba(14,165,233,0.1) !important; color:rgba(14,165,233,1) !important; }
.bg-sky-500 { background-color:rgba(14,165,233,1) !important; color:#0f172a !important; }
.bg-sky-600 { background-color:rgba(2,132,199,1) !important; color:#e0f2fe !important; }

.bg-blue-500 { background-color:rgba(59,130,246,1) !important; color:#fff !important; }
.bg-blue-500\\/10 { background-color:rgba(59,130,246,0.1) !important; color:rgba(59,130,246,1) !important; }
.bg-blue-600 { background-color:rgba(37,99,235,1) !important; color:#fff !important; }
.bg-blue-700 { background-color:rgba(29,78,216,1) !important; color:#fff !important; }

.bg-green-500 { background-color:rgba(16,185,129,1) !important; color:#022c22 !important; }
.bg-green-500\\/10 { background-color:rgba(16,185,129,0.1) !important; color:rgba(16,185,129,1) !important; }
.bg-green-500\\/20 { background-color:rgba(16,185,129,0.2) !important; color:rgba(16,185,129,1) !important; }

.bg-emerald-500\\/15 { background-color:rgba(16,185,129,0.15) !important; color:rgba(16,185,129,1) !important; }
.bg-emerald-400\\/15 { background-color:rgba(74,222,128,0.15) !important; }

.bg-purple-500\\/10 { background-color:rgba(168,85,247,0.1) !important; color:rgba(168,85,247,1) !important; }
.bg-orange-500\\/10 { background-color:rgba(249,115,22,0.1) !important; color:rgba(249,115,22,1) !important; }

.bg-red-500 { background-color:rgba(239,68,68,1) !important; color:#fff !important; }
.bg-red-500\\/10 { background-color:rgba(239,68,68,0.1) !important; color:rgba(239,68,68,1) !important; }
.bg-red-500\\/20 { background-color:rgba(239,68,68,0.2) !important; color:rgba(239,68,68,1) !important; }
.bg-red-500\\/30 { background-color:rgba(239,68,68,0.3) !important; color:rgba(239,68,68,1) !important; }

.bg-yellow-500 { background-color:rgba(234,179,8,1) !important; color:#000 !important; }

/* 玻璃态模糊 */
.backdrop-blur-md {
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
}
.backdrop-blur-xl {
  -webkit-backdrop-filter: blur(24px);
  backdrop-filter: blur(24px);
}
.backdrop-blur {
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
}

/* ===== 字体 / 文本颜色 / 对齐 / 细节 ===== */
.font-sans { font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif !important; }
.font-mono { font-family:'JetBrains Mono','Fira Code',ui-monospace,monospace !important; }
.font-medium { font-weight:500 !important; }
.font-semibold { font-weight:600 !important; }
.antialiased { -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }

.text-left { text-align:left !important; }
.text-center { text-align:center !important; }

.text-xs { font-size:0.75rem !important; line-height:1rem !important; }
.text-sm { font-size:0.875rem !important; line-height:1.25rem !important; }
.text-lg { font-size:1.125rem !important; line-height:1.75rem !important; }
.text-xl { font-size:1.25rem !important; line-height:1.75rem !important; }
.text-2xl { font-size:1.5rem !important; line-height:2rem !important; }
.text-3xl { font-size:1.875rem !important; line-height:2.25rem !important; }
.text-4xl { font-size:2.25rem !important; line-height:2.5rem !important; }

.text-white { color:#ffffff !important; }
.text-gray-400 { color:rgba(156,163,175,1) !important; }
.text-gray-500 { color:rgba(107,114,128,1) !important; }
.text-gray-600 { color:rgba(75,85,99,1) !important; }
.text-gray-700 { color:rgba(55,65,81,1) !important; }
.text-gray-900 { color:rgba(17,24,39,1) !important; }

.text-slate-100 { color:rgba(241,245,249,1) !important; }
.text-slate-200 { color:rgba(226,232,240,1) !important; }
.text-slate-300 { color:rgba(203,213,225,1) !important; }
.text-slate-400 { color:rgba(148,163,184,1) !important; }
.text-slate-500 { color:rgba(100,116,139,1) !important; }
.text-slate-900 { color:rgba(15,23,42,1) !important; }

.text-zinc-300 { color:rgba(212,212,216,1) !important; }
.text-zinc-400 { color:rgba(161,161,170,1) !important; }
.text-zinc-500 { color:rgba(113,113,122,1) !important; }

.text-blue-500 { color:rgba(59,130,246,1) !important; }
.text-green-500 { color:rgba(16,185,129,1) !important; }
.text-emerald-300 { color:rgba(110,231,183,1) !important; }
.text-emerald-400 { color:rgba(74,222,128,1) !important; }
.text-red-400 { color:rgba(248,113,113,1) !important; }
.text-red-500 { color:rgba(239,68,68,1) !important; }
.text-orange-500 { color:rgba(249,115,22,1) !important; }
.text-purple-500 { color:rgba(168,85,247,1) !important; }
.text-yellow-400 { color:rgba(250,204,21,1) !important; }
.text-sky-200 { color:rgba(186,230,253,1) !important; }
.text-sky-300 { color:rgba(125,211,252,1) !important; }

.uppercase { text-transform:uppercase !important; }

/* ===== 动画 / 透明度 / 过渡 / hover ===== */
.opacity-60 { opacity:0.6 !important; }
.opacity-80 { opacity:0.8 !important; }
.animate-pulse {
  animation:pulse 1.5s cubic-bezier(0.4,0,0.6,1) infinite !important;
}
@keyframes pulse {
  0%,100% { opacity:1; }
  50% { opacity:0.5; }
}

.transition { transition: all .2s ease-in-out !important; }
.transition-all { transition: all .25s ease-in-out !important; }
.transition-colors {
  transition-property: color, background-color, border-color, text-decoration-color, fill, stroke !important;
  transition-duration:150ms !important;
}
.duration-300 { transition-duration:300ms !important; }

.hover\\:bg-slate-900\\/5:hover { background-color:rgba(15,23,42,0.05) !important; }
.hover\\:bg-slate-900\\/20:hover { background-color:rgba(15,23,42,0.2) !important; }
.hover\\:bg-slate-900\\/30:hover { background-color:rgba(15,23,42,0.3) !important; }
.hover\\:bg-gray-50:hover { background-color:rgba(249,250,251,1) !important; }
.hover\\:bg-red-50:hover { background-color:rgba(254,242,242,1) !important; }
.hover\\:bg-sky-600:hover { background-color:rgba(2,132,199,1) !important; color:#e0f2fe !important; }
.hover\\:bg-red-500\\/10:hover { background-color:rgba(239,68,68,0.1) !important; }
.hover\\:bg-red-500\\/30:hover { background-color:rgba(239,68,68,0.3) !important; }
.hover\\:shadow-md:hover { box-shadow:0 20px 40px rgba(0,0,0,0.45) !important; }
.hover\\:shadow-xl:hover { box-shadow:0 20px 50px -12px rgba(15,23,42,0.5) !important; }

/* 文本截断 */
.truncate {
  overflow:hidden !important;
  text-overflow:ellipsis !important;
  white-space:nowrap !important;
}
`;

  // 父窗口监听 iframe 的报错
  window.addEventListener("message", (event) => {
    if (!event || !event.data || event.source !== frame.contentWindow) return;
    if (event.data.type === "CODE_PLAYGROUND_ERROR") {
      showError(event.data.message || "运行时出现错误", "运行时错误");
    }
  });

  // 左侧编辑器的默认示例（你可以无视它，直接粘贴 RemoteDesktopUI）
  const DEFAULT_SOURCE = `import React, { useState } from 'react';
import { Monitor, Smartphone, Settings, Sun, Moon, Wifi, Gamepad2 } from 'lucide-react';

const devices = [
  { id: 1, name: '我的工作电脑', delay: '5ms', status: 'online' },
  { id: 2, name: '家里的 MacBook', delay: '12ms', status: 'online' },
  { id: 3, name: 'Linux 服务器', delay: '-', status: 'offline' }
];

export default function RemoteDesktopDemo() {
  const [darkMode, setDarkMode] = useState(true);
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
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-900/20 hover:bg-slate-900/30 text-sm"
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

  // 状态/错误显示
  function setStatus(message, state = "idle") {
    const span = statusLabel.querySelector("span:last-child");
    span.textContent = message;
    statusLabel.dataset.state = state;
  }

  function setCompileInfo(message, good = true) {
    compileBadge.textContent = message;
    compileBadge.style.background = good
      ? "rgba(56,189,248,0.18)"
      : "rgba(248,113,113,0.12)";
    compileBadge.style.color = good ? "#38bdf8" : "#f87171";
    if (compilerRetryButton && good) {
      compilerRetryButton.classList.remove("is-visible");
    }
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

  // ========== Babel 加载 ==========
  function isBabelReady() {
    return Boolean(window.Babel && typeof window.Babel.transform === "function");
  }

  function ensureBabelLoaded() {
    if (isBabelReady()) return Promise.resolve();
    if (babelLoadingPromise) return babelLoadingPromise;

    setCompileInfo("加载编译器…", true);
    setStatus("加载 Babel 编译器", "running");

    const existingScript = document.querySelector("[data-babel-loader]");
    const sources = BABEL_SOURCES.slice();
    if (existingScript && existingScript.src) {
      sources.unshift(existingScript.src);
    }

    babelLoadingPromise = new Promise((resolve, reject) => {
      let index = 0;

      const attempt = () => {
        if (isBabelReady()) {
          resolve();
          return;
        }
        if (index >= sources.length) {
          reject(new Error("无法加载 Babel 编译器，预览功能不可用。"));
          return;
        }

        const src = sources[index++];
        let script = null;
        let timeoutId = null;

        if (
          existingScript &&
          existingScript.src === src &&
          !existingScript.dataset.babelTried
        ) {
          script = existingScript;
          script.dataset.babelTried = "true";
        } else {
          script = document.createElement("script");
          script.src = src;
          script.async = true;
          script.crossOrigin = "anonymous";
          script.dataset.injected = "true";
          document.head.appendChild(script);
        }

        const cleanup = () => {
          script.removeEventListener("load", handleLoad);
          script.removeEventListener("error", handleError);
          if (timeoutId) {
            clearTimeout(timeoutId);
            timeoutId = null;
          }
        };

        function handleLoad() {
          setTimeout(() => {
            cleanup();
            if (isBabelReady()) {
              resolve();
            } else {
              attempt();
            }
          }, 0);
        }

        function handleError() {
          cleanup();
          if (script !== existingScript) script.remove();
          attempt();
        }

        script.addEventListener("load", handleLoad);
        script.addEventListener("error", handleError, { once: true });
        timeoutId = setTimeout(() => {
          cleanup();
          if (script !== existingScript) script.remove();
          attempt();
        }, BABEL_ATTEMPT_TIMEOUT);

        setCompileInfo(
          "加载编译器…(" + index + "/" + sources.length + ")",
          true
        );
        setStatus("加载 Babel 编译器", "running");
      };

      attempt();
    })
      .then(() => {
        setCompileInfo("编译器已就绪", true);
        setStatus("实时预览", "idle");
        if (compilerRetryButton) {
          compilerRetryButton.classList.remove("is-visible");
        }
      })
      .catch((error) => {
        setCompileInfo("编译器加载失败", false);
        throw error;
      })
      .finally(() => {
        babelLoadingPromise = null;
      });

    return babelLoadingPromise;
  }

  // ========== 源码 -> Babel -> iframe HTML ==========
  function normalizeSource(source) {
    return source.replace(/\t/g, "  ");
  }

  function buildPreviewHtml(compiledCode) {
    const encodedCode = JSON.stringify(compiledCode);

    const polyfills = Object.entries(CDN_POLYFILLS)
      .map(([_, url]) => `<script crossorigin src="${url}"></script>`)
      .join("\n");

    return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
<style>
${CORE_CSS}
</style>
${polyfills}
<script>
  // ReactDOM <18 fallback
  window.ReactDOMClient = window.ReactDOM;
  if (!window.ReactDOMClient || !window.ReactDOMClient.createRoot) {
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

  // lucide-react fallback: 如果 CDN 没成功加载，就用圆形字母占位
  window.lucideReact = window.lucideReact || window.lucide;
  if (!window.lucideReact) {
    const fallback = new Proxy({}, {
      get: function (_, iconName) {
        return function IconStub(props) {
          const size = props && props.size ? props.size : 16;
          const label = typeof iconName === 'string'
            ? iconName.slice(0,2).toUpperCase()
            : 'I';
          return window.React.createElement(
            'span',
            {
              style: {
                display:'inline-flex',
                alignItems:'center',
                justifyContent:'center',
                width:size+'px',
                height:size+'px',
                borderRadius:'50%',
                background:'rgba(148,163,184,0.18)',
                color:'#94a3b8',
                fontSize:(size*0.45)+'px',
                fontWeight:600,
                textTransform:'uppercase'
              }
            },
            label
          );
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

  function createIconStub(name) {
    return function IconStub(props) {
      const size = (props && props.size) || 16;
      const label = typeof name === 'string' ? name.slice(0, 2).toUpperCase() : 'I';
      return window.React.createElement(
        'span',
        {
          style: {
            display:'inline-flex',
            alignItems:'center',
            justifyContent:'center',
            width:size+'px',
            height:size+'px',
            borderRadius:'50%',
            background:'rgba(148,163,184,0.18)',
            color:'#94a3b8',
            fontSize:(size*0.45)+'px',
            fontWeight:600,
            textTransform:'uppercase'
          }
        },
        label || 'I'
      );
    };
  }

  function createLucideModule(mod) {
    const source = mod && mod.default && Object.keys(mod).length === 1 ? mod.default : mod;
    const base = wrapModule(source || {});
    const cache = {};
    return new Proxy(base, {
      get(target, prop, receiver) {
        if (prop === '__esModule' || prop === Symbol.toStringTag) return true;
        if (prop === 'default') return base.default;
        if (prop in target) return Reflect.get(target, prop, receiver);
        if (source && source[prop]) {
          target[prop] = source[prop];
          return target[prop];
        }
        if (source && source.icons && source.icons[prop]) {
          target[prop] = source.icons[prop];
          return target[prop];
        }
        if (!cache[prop]) {
          cache[prop] = createIconStub(prop);
          try {
            Object.defineProperty(target, prop, {
              configurable:true,
              enumerable:true,
              writable:true,
              value: cache[prop],
            });
          } catch(_) {
            target[prop] = cache[prop];
          }
        }
        return cache[prop];
      }
    });
  }

  function reportError(payload) {
    if (window.parent && window.parent !== window) {
      const message =
        typeof payload === 'string'
          ? payload
          : (payload && (payload.stack || payload.message)) || 'Unknown error';
      window.parent.postMessage({ type: 'CODE_PLAYGROUND_ERROR', message }, '*');
    }
  }

  const requireMap = {
    react: (function () { return wrapModule(window.React || {}); })(),
    'react-dom': (function () { return wrapModule(window.ReactDOM || {}); })(),
    'react-dom/client': (function () { return wrapModule(window.ReactDOMClient || window.ReactDOM || {}); })(),
    'react/jsx-runtime': createJsxRuntimeModule(),
    'react/jsx-dev-runtime': createJsxRuntimeModule(),
    'lucide-react': (function () {
      const mod = window.lucideReact || window.lucide || {};
      return createLucideModule(mod);
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
    const factory = new Function(
      'exports','require','module','__filename','__dirname',
      __compiled
    );
    factory(exports, require, module, 'App.jsx', '/');

    const App =
      module.exports?.default ||
      module.exports.App ||
      module.exports;

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
</html>
`;
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

  // ========== 刷新预览 / 去抖 ==========
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

  function handleBabelFailure(error) {
    const message =
      (error && error.message) ||
      "无法加载 Babel 编译器，暂时无法编译预览。";
    const guidance =
      message + "\n请检查网络连接或点击“重试编译器”按钮后再试。";
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

  // ========== 顶部按钮行为 ==========
  function handleAction(event) {
    const action = event.currentTarget.dataset.action;
    if (action === "reset") {
      editor.value = DEFAULT_SOURCE;
      localStorage.removeItem(STORAGE_KEY);
      scheduleUpdate(true);
    }
    if (action === "copy") {
      navigator.clipboard
        .writeText(editor.value)
        .then(() => {
          setStatus("已复制到剪贴板", "success");
          setTimeout(() => setStatus("实时预览"), 1600);
        })
        .catch(() => {
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

  // ========== init ==========
  function init() {
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
