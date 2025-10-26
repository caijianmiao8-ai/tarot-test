(function () {
  const editor = document.getElementById("code-editor");
  const frame = document.getElementById("preview-frame");
  const overlay = document.getElementById("error-overlay");
  const compileBadge = document.getElementById("compile-info");
  const statusLabel = document.getElementById("status-label");
  const buttons = document.querySelectorAll("[data-action]");
  const compilerRetryButton = document.querySelector('[data-action="reload-compiler"]');

  const STORAGE_KEY = "code-playground-source";
  const COMPILE_ENDPOINT = "/api/compile-preview";
  const REQUEST_DEBOUNCE = 320;

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

  let debounceTimer = null;
  let lastSource = "";
  let currentBlobUrl = null;
  let activeRequestId = 0;
  let currentController = null;

  function setStatus(message, state = "idle") {
    const span = statusLabel.querySelector("span:last-child");
    if (span) {
      span.textContent = message;
    }
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

  window.addEventListener("message", (event) => {
    if (!event || !event.data || event.source !== frame.contentWindow) return;
    if (event.data.type === "CODE_PLAYGROUND_ERROR") {
      showError(event.data.message || "运行时出现错误", "运行时错误");
    }
  });

  function sanitizeScriptContent(js) {
    return (js || "")
      .replace(/<\/script>/gi, "<\\/script>")
      .replace(/<script/gi, "<\\script>")
      .replace(/<\/style>/gi, "<\\/style>");
  }

  /**
   * 🔥 关键修改：添加 CDN script 标签
   */
  function buildPreviewHtml(js, css) {
    const script = sanitizeScriptContent(js);
    const styles = css || "";
    
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <style id="tailwind-bundle">
${styles}
  </style>
  <style>
    body { 
      margin:0; 
      background:#020617; 
      color:#e2e8f0; 
      font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif; 
    }
  </style>
</head>
<body style="margin:0;">
  <div id="root"></div>
  
  <!-- 🔥 CDN 依赖加载 -->
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/lucide-react@0.263.1/dist/umd/lucide-react.js"></script>
  
  <!-- 用户编译后的代码 -->
  <script>
${script}
  </script>
</body>
</html>`;
  }

  function applyPreview(js, css) {
    const html = buildPreviewHtml(js, css);
    
    // 清理旧的 Blob URL
    if (currentBlobUrl) {
      try {
        URL.revokeObjectURL(currentBlobUrl);
      } catch (err) {
        console.warn("Failed to revoke blob URL:", err);
      }
      currentBlobUrl = null;
    }

    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    currentBlobUrl = url;

    frame.removeAttribute("srcdoc");
    frame.src = url;

    // 清理超时
    const cleanupTimeout = setTimeout(() => {
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (err) {
          console.warn("Timeout cleanup failed:", err);
        }
      }
    }, 10000);

    frame.onload = () => {
      clearTimeout(cleanupTimeout);
      if (currentBlobUrl === url) {
        try {
          URL.revokeObjectURL(url);
          currentBlobUrl = null;
        } catch (err) {
          console.warn("onload cleanup failed:", err);
        }
      }
    };

    frame.onerror = () => {
      clearTimeout(cleanupTimeout);
      try {
        URL.revokeObjectURL(url);
        if (currentBlobUrl === url) {
          currentBlobUrl = null;
        }
      } catch (err) {
        console.warn("onerror cleanup failed:", err);
      }
    };
  }

  function handleCompileSuccess(js, css) {
    hideError();
    applyPreview(js, css);
    setCompileInfo("编译成功", true);
    setStatus("实时预览", "idle");
  }

  function handleCompileError(message) {
    showError(message || "编译失败");
    if (compilerRetryButton) {
      compilerRetryButton.classList.add("is-visible");
    }
  }

  async function requestPreview(source, requestId) {
    if (currentController) {
      currentController.abort();
    }

    const controller = new AbortController();
    currentController = controller;

    setCompileInfo("编译中…", true);
    setStatus("编译中", "running");
    hideError();

    // 添加超时保护
    const timeoutId = setTimeout(() => {
      controller.abort();
      if (requestId === activeRequestId) {
        handleCompileError("编译超时（30秒），请检查代码复杂度");
      }
    }, 30000);

    try {
      const response = await fetch(COMPILE_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
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
          if (data && data.error) {
            errorMessage = data.error;
          }
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
      
      if (error.name === "AbortError") {
        return;
      }
      if (requestId !== activeRequestId || currentController !== controller) {
        return;
      }
      handleCompileError(error.message || "网络异常，请稍后重试");
    } finally {
      if (currentController === controller) {
        currentController = null;
      }
    }
  }

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

  function handleAction(event) {
    const action = event.currentTarget.dataset.action;
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

  function init() {
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